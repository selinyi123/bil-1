#!/usr/bin/env python3
"""打「解压即用」私人包（Windows 安全打包，不破坏 .app）。

重要：绝不能在 Windows 上解压再重打 Binggo.app——会弄坏 Frameworks 里的
符号链接，macOS 会出现「无法打开 / 访达没有权限打开 (null)」。

正确做法：
1. 原样嵌入 CI 产出的 Binggo-macOS-arm64.zip（不改内部）
2. 附带完整 config/ + data/
3. 附带 Mac 端「一键启动.command」：在 Mac 上 unzip → chmod/xattr → 便携启动

产物默认：
  dist/private/Binggo-v{version}-Private-Ready-macOS.zip
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import stat
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ASCII 文件名，避免部分解压工具乱码
_LAUNCHER_NAME = "Start-Binggo.command"

_LAUNCHER = """#!/bin/bash
# Binggo private ready launcher (run on Mac only)
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

APP="$DIR/Binggo.app"
VENDOR_ZIP="$DIR/vendor/Binggo-macOS-arm64.zip"

if [ ! -d "$APP" ]; then
  if [ ! -f "$VENDOR_ZIP" ]; then
    echo "缺少 vendor/Binggo-macOS-arm64.zip" >&2
    exit 1
  fi
  echo "正在解压 Binggo.app（仅首次）…"
  unzip -qo "$VENDOR_ZIP" -d "$DIR"
fi

if [ ! -d "$DIR/config" ] || [ ! -f "$DIR/data/binggo.db" ]; then
  echo "缺少同级 config/ 或 data/binggo.db，请完整解压本私人包。" >&2
  exit 1
fi

# 清除隔离属性并恢复可执行位（从网盘/Windows 拷过来常见）
xattr -cr "$APP" 2>/dev/null || true
chmod +x "$APP/Contents/MacOS/Binggo" 2>/dev/null || true
if [ -f "$DIR/BinggoPortable.command" ]; then
  chmod +x "$DIR/BinggoPortable.command" 2>/dev/null || true
fi

export BINGGO_PORTABLE=1
echo "启动 Binggo（便携模式，数据=本目录 config/data）…"
echo "控制台: http://127.0.0.1:8181"
exec "$APP/Contents/MacOS/Binggo"
"""


def _version() -> str:
    text = (ROOT / "src" / "app_paths.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.M)
    return match.group(1) if match else "unknown"


def _load_build_bundle():
    spec = importlib.util.spec_from_file_location(
        "export_migrate_bundle",
        Path(__file__).resolve().parent / "export_migrate_bundle.py",
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod.build_bundle


def _write_readme(path: Path, version: str, db: dict) -> None:
    tables = (db or {}).get("tables") or {}
    lines = [
        f"Binggo v{version} 私人「解压即用」包（含完整数据）",
        f"生成时间（UTC）: {datetime.now(timezone.utc).isoformat()}",
        "",
        "【必读】请用本包里的 Start-Binggo.command 启动，不要直接双击尚未解压出来的残缺 .app。",
        "",
        "怎么用",
        "------",
        "1. 把整个 zip 拷到 Mac，解压到任意文件夹",
        "2. 右键 Start-Binggo.command → 打开",
        "   （首次会自动解压 vendor 里的原版 Binggo.app，并带上同级 config/data）",
        "3. 浏览器打开 http://127.0.0.1:8181",
        "",
        "若提示无权限，在该文件夹打开「终端」执行：",
        f"  chmod +x {_LAUNCHER_NAME}",
        f"  xattr -cr {_LAUNCHER_NAME}",
        f"  ./{_LAUNCHER_NAME}",
        "",
        "目录说明",
        "--------",
        f"  {_LAUNCHER_NAME}     ← 请用这个启动",
        "  vendor/Binggo-macOS-arm64.zip  ← 原版应用（勿在 Windows 里解压再拷）",
        "  config/  data/        ← 你的完整状态（Cookie/LLM/数据库）",
        "  README.txt",
        "",
        "数据摘要",
        "--------",
    ]
    for key, label in (
        ("activities", "活动"),
        ("watch_users", "监控用户"),
        ("participations", "参与记录"),
        ("jobs", "任务"),
        ("source_checkpoints", "数据源检查点"),
    ):
        if key in tables:
            lines.append(f"  - {label}: {tables[key]}")
    lines.extend(
        [
            "",
            "注意",
            "----",
            "- 保持 Start 脚本、config、data、vendor 在同一文件夹。",
            "- 含隐私凭证，仅限私人电脑。",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def _zip_tree(src_dir: Path, out_zip: Path) -> None:
    if out_zip.exists():
        out_zip.unlink()
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(src_dir.rglob("*")):
            if not path.is_file():
                continue
            arc = path.relative_to(src_dir).as_posix()
            info = zipfile.ZipInfo.from_file(path, arcname=arc)
            if path.name.endswith(".command"):
                info.external_attr = 0o755 << 16
            else:
                info.external_attr = (stat.S_IMODE(path.stat().st_mode) << 16)
            # Store nested mac zip without recompression if already compressed heavily
            compress = zipfile.ZIP_STORED if path.suffix.lower() == ".zip" and "vendor" in path.parts else zipfile.ZIP_DEFLATED
            with path.open("rb") as fh:
                zf.writestr(info, fh.read(), compress_type=compress)


def build_ready(
    *,
    mac_zip: Path,
    source_home: Path,
    appdata_home: Path | None,
    out_zip: Path,
) -> dict:
    if not mac_zip.is_file():
        raise FileNotFoundError(mac_zip)

    build_bundle = _load_build_bundle()
    version = _version()

    with tempfile.TemporaryDirectory(prefix="binggo-ready-") as tmp:
        tmp_path = Path(tmp)
        stage = tmp_path / "Binggo-Private-Ready"
        vendor = stage / "vendor"
        stage.mkdir()
        vendor.mkdir()

        # 原样复制 CI 产物，绝不解压 .app
        nested = vendor / "Binggo-macOS-arm64.zip"
        nested.write_bytes(mac_zip.read_bytes())

        launcher = stage / _LAUNCHER_NAME
        launcher.write_text(_LAUNCHER.replace("\r\n", "\n"), encoding="utf-8", newline="\n")

        userdata_zip = tmp_path / "userdata.zip"
        report = build_bundle(
            source_home=source_home,
            appdata_home=appdata_home,
            out_zip=userdata_zip,
        )
        with zipfile.ZipFile(userdata_zip, "r") as zf:
            for name in zf.namelist():
                if name in {"MIGRATE_README.txt", "migrate-manifest.json"}:
                    continue
                if not (name.startswith("config/") or name.startswith("data/")):
                    continue
                zf.extract(name, stage)

        _write_readme(stage / "README.txt", version, report.get("db") or {})
        (stage / "private-ready-manifest.json").write_text(
            json.dumps(
                {
                    "version": version,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "mode": "portable-ready-nested-app",
                    "launcher": _LAUNCHER_NAME,
                    "note": "Binggo.app is extracted on Mac only; never re-zipped on Windows",
                    "userdata": {
                        k: report[k]
                        for k in (
                            "file_count",
                            "merged_from_appdata",
                            "db",
                            "source_home",
                        )
                        if k in report
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        _zip_tree(stage, out_zip)

    return {
        "out_zip": str(out_zip),
        "size_bytes": out_zip.stat().st_size,
        "version": version,
        "mode": "portable-ready-nested-app",
        "launcher": _LAUNCHER_NAME,
        "db": report.get("db"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="打包解压即用的私人 macOS 包")
    parser.add_argument(
        "--mac-zip",
        type=Path,
        default=ROOT
        / "dist"
        / "private"
        / "macos-build"
        / "Binggo-macOS-arm64.zip",
    )
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--no-appdata", action="store_true")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    version = _version()
    out = args.out or (
        ROOT / "dist" / "private" / f"Binggo-v{version}-Private-Ready-macOS.zip"
    )
    appdata = None
    if not args.no_appdata and os.environ.get("APPDATA"):
        appdata = Path(os.environ["APPDATA"]) / "Binggo"

    report = build_ready(
        mac_zip=args.mac_zip.resolve(),
        source_home=args.source.resolve(),
        appdata_home=appdata.resolve() if appdata else None,
        out_zip=out.resolve(),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
