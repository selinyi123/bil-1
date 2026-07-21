#!/usr/bin/env python3
"""打包「私人完整迁移版」：macOS 安装包 + 全量用户数据。

产物（默认）：
  dist/private/Binggo-v{version}-Private-Complete-macOS.zip

结构：
  README.txt
  app/Binggo-macOS-arm64.dmg
  app/Binggo-macOS-arm64.zip
  userdata/config/…
  userdata/data/…   （含 binggo.db、Cookie、LLM、任务等）
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

import importlib.util

_spec = importlib.util.spec_from_file_location(
    "export_migrate_bundle",
    Path(__file__).resolve().parent / "export_migrate_bundle.py",
)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)
build_bundle = _mod.build_bundle


def _version() -> str:
    import re

    text = (ROOT / "src" / "app_paths.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.M)
    return match.group(1) if match else "unknown"


def _readme(version: str, db_summary: dict) -> str:
    tables = (db_summary or {}).get("tables") or {}
    highlights = []
    for key, label in (
        ("activities", "活动"),
        ("watch_users", "监控用户"),
        ("participations", "参与记录"),
        ("jobs", "任务"),
        ("source_checkpoints", "数据源检查点"),
    ):
        if key in tables:
            highlights.append(f"  - {label}: {tables[key]}")

    return "\n".join(
        [
            f"Binggo v{version} 私人完整迁移包（macOS Apple Silicon）",
            f"生成时间（UTC）: {datetime.now(timezone.utc).isoformat()}",
            "",
            "本包内容",
            "--------",
            "1) app/ 下的 dmg + zip：私人构建的 Binggo.app（未挂公开 Release）",
            "2) userdata/：你的完整本地状态（SQLite、Cookie、LLM、缓存、日志等）",
            "",
            "数据库摘要",
            "----------",
            *highlights,
            "",
            "推荐安装方式（默认安装模式）",
            "----------------------------",
            "1. 把 app/Binggo-macOS-arm64.dmg 拷到 Mac，打开后把 Binggo 拖到「应用程序」",
            "   （或解压 app/Binggo-macOS-arm64.zip 得到 Binggo.app）",
            "2. 完全退出 Binggo（若已打开）",
            "3. 在终端执行：",
            '     mkdir -p "$HOME/Library/Application Support/Binggo"',
            '     cp -R userdata/config userdata/data "$HOME/Library/Application Support/Binggo/"',
            "4. 首次请右键「应用程序」里的 Binggo → 打开",
            "5. 浏览器打开 http://127.0.0.1:8181 ，确认账号 / 活动 / 监控 / LLM",
            "",
            "便携方式（数据跟 .app 放一起）",
            "------------------------------",
            "1. 解压 Binggo-macOS-arm64.zip，得到 Binggo.app（及便携脚本若有）",
            "2. 把 userdata 里的 config/、data/ 放到与 Binggo.app 同级目录",
            "3. 用包内 BinggoPortable.command 启动（会设 BINGGO_PORTABLE=1）",
            "   或：export BINGGO_PORTABLE=1 后启动 Binggo.app",
            "",
            "注意",
            "----",
            "- 本包含 Cookie / API Key，仅限你私人电脑使用，勿上传网盘公开分享。",
            "- 覆盖 userdata 前请先退出 Binggo，避免数据库锁。",
            "- Intel Mac 不能用此 arm64 包，请改用源码运行。",
            "",
        ]
    )


def build_complete(
    *,
    mac_dmg: Path,
    mac_zip: Path,
    source_home: Path,
    appdata_home: Path | None,
    out_zip: Path,
) -> dict:
    if not mac_dmg.is_file() or not mac_zip.is_file():
        raise FileNotFoundError(
            f"缺少 macOS 产物: dmg={mac_dmg} zip={mac_zip}"
        )

    version = _version()
    with tempfile.TemporaryDirectory(prefix="binggo-private-") as tmp:
        tmp_path = Path(tmp)
        userdata_zip = tmp_path / "userdata.zip"
        report = build_bundle(
            source_home=source_home,
            appdata_home=appdata_home,
            out_zip=userdata_zip,
        )

        staging = tmp_path / "staging"
        userdata_dir = staging / "userdata"
        app_dir = staging / "app"
        userdata_dir.mkdir(parents=True)
        app_dir.mkdir(parents=True)

        with zipfile.ZipFile(userdata_zip, "r") as zf:
            for name in zf.namelist():
                if name in {"MIGRATE_README.txt", "migrate-manifest.json"}:
                    # 说明合并进总 README；manifest 仍保留
                    if name == "migrate-manifest.json":
                        zf.extract(name, staging)
                    continue
                zf.extract(name, userdata_dir)

        shutil.copy2(mac_dmg, app_dir / mac_dmg.name)
        shutil.copy2(mac_zip, app_dir / mac_zip.name)
        (staging / "README.txt").write_text(
            _readme(version, report.get("db") or {}),
            encoding="utf-8",
        )
        if (staging / "migrate-manifest.json").exists():
            (staging / "migrate-manifest.json").replace(
                staging / "userdata-manifest.json"
            )

        out_zip.parent.mkdir(parents=True, exist_ok=True)
        if out_zip.exists():
            out_zip.unlink()

        with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(staging.rglob("*")):
                if path.is_file():
                    zf.write(path, arcname=path.relative_to(staging).as_posix())

    size = out_zip.stat().st_size
    return {
        "out_zip": str(out_zip),
        "size_bytes": size,
        "version": version,
        "userdata": report,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="打包私人完整 macOS 迁移版")
    parser.add_argument(
        "--mac-dir",
        type=Path,
        default=ROOT / "dist" / "private" / "macos-build",
        help="含 Binggo-macOS-arm64.dmg/.zip 的目录",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=ROOT,
        help="用户数据主目录（默认仓库根）",
    )
    parser.add_argument(
        "--no-appdata",
        action="store_true",
        help="不合并 %%APPDATA%%\\Binggo",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="输出 zip；默认 dist/private/Binggo-vX-Private-Complete-macOS.zip",
    )
    args = parser.parse_args()
    version = _version()
    out = args.out or (
        ROOT / "dist" / "private" / f"Binggo-v{version}-Private-Complete-macOS.zip"
    )
    appdata = None
    if not args.no_appdata and os.environ.get("APPDATA"):
        appdata = Path(os.environ["APPDATA"]) / "Binggo"

    report = build_complete(
        mac_dmg=args.mac_dir / "Binggo-macOS-arm64.dmg",
        mac_zip=args.mac_dir / "Binggo-macOS-arm64.zip",
        source_home=args.source.resolve(),
        appdata_home=appdata.resolve() if appdata else None,
        out_zip=out.resolve(),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
