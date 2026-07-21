#!/usr/bin/env python3
"""导出完整用户数据目录，便于 Windows → macOS 迁移。

默认打包「当前仓库开发态」的 config/ + data/（含 binggo.db、Cookie、LLM 等），
并可选合并 %APPDATA%\\Binggo 中仓库里没有的文件。

产物默认：dist/private/Binggo-userdata-migrate.zip
解压到 Mac 后整目录内容应放到：
  ~/Library/Application Support/Binggo/
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 开发杂讯，默认不打进迁移包（不影响运行时状态）
SKIP_NAME_PREFIXES = (
    "diag_out",
    "probe_",
    "tmp_diag",
)
SKIP_SUFFIXES = (
    ".pyc",
    ".db-shm",
    ".db-wal",
    ".db-journal",
)


def _should_skip(rel: Path) -> bool:
    name = rel.name
    if name.startswith(".") and name not in {".gitkeep"}:
        # 保留 .star 等无；跳过常见隐藏杂讯
        if name in {".DS_Store", "Thumbs.db"}:
            return True
    if any(name.startswith(p) for p in SKIP_NAME_PREFIXES):
        return True
    if name.endswith(SKIP_SUFFIXES):
        return True
    if "__pycache__" in rel.parts:
        return True
    return False


def _sqlite_consistent_copy(src: Path, dst: Path) -> None:
    """用 SQLite Backup API 导出一致性快照，避免拷到半截 WAL。"""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    src_con = sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True)
    try:
        dst_con = sqlite3.connect(dst.as_posix())
        try:
            src_con.backup(dst_con)
            dst_con.commit()
        finally:
            dst_con.close()
    finally:
        src_con.close()


def _iter_files(base: Path) -> list[Path]:
    if not base.is_dir():
        return []
    out: list[Path] = []
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(base)
        if _should_skip(rel):
            continue
        out.append(path)
    return sorted(out)


def _db_summary(db_path: Path) -> dict:
    if not db_path.is_file():
        return {"exists": False}
    try:
        con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        cur = con.cursor()
        tables = [
            r[0]
            for r in cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY 1"
            )
        ]
        counts = {}
        for t in tables:
            try:
                counts[t] = cur.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            except sqlite3.Error:
                counts[t] = None
        con.close()
        return {
            "exists": True,
            "size_bytes": db_path.stat().st_size,
            "tables": counts,
        }
    except sqlite3.Error as exc:
        return {"exists": True, "error": str(exc), "size_bytes": db_path.stat().st_size}


def build_bundle(
    *,
    source_home: Path,
    appdata_home: Path | None,
    out_zip: Path,
) -> dict:
    staging: dict[str, Path] = {}

    for sub in ("config", "data"):
        base = source_home / sub
        for path in _iter_files(base):
            rel = Path(sub) / path.relative_to(base)
            staging[rel.as_posix()] = path

    merged_from_appdata: list[str] = []
    if appdata_home and appdata_home.is_dir():
        for sub in ("config", "data"):
            base = appdata_home / sub
            for path in _iter_files(base):
                rel = Path(sub) / path.relative_to(base)
                key = rel.as_posix()
                if key not in staging:
                    staging[key] = path
                    merged_from_appdata.append(key)

    out_zip.parent.mkdir(parents=True, exist_ok=True)
    if out_zip.exists():
        out_zip.unlink()

    db_key = "data/binggo.db"
    db_src = staging.get(db_key)
    tmp_db: Path | None = None
    if db_src and db_src.is_file():
        tmp_db = out_zip.parent / f".binggo-migrate-{os.getpid()}.db"
        _sqlite_consistent_copy(db_src, tmp_db)
        staging[db_key] = tmp_db

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_home": str(source_home),
        "appdata_home": str(appdata_home) if appdata_home else None,
        "file_count": len(staging),
        "merged_from_appdata": merged_from_appdata,
        "db": _db_summary(staging[db_key] if db_key in staging else source_home / "data" / "binggo.db"),
        "mac_restore_path": "~/Library/Application Support/Binggo",
        "notes": [
            "解压后得到 config/ 与 data/，整体放入 mac_restore_path。",
            "先退出 Mac 上的 Binggo，再覆盖目标目录。",
            "默认安装模式读 Application Support；便携模式则放到 .app 同级目录。",
        ],
    }

    try:
        with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for key in sorted(staging):
                zf.write(staging[key], arcname=key)
            zf.writestr(
                "MIGRATE_README.txt",
                "\n".join(
                    [
                        "Binggo 用户数据迁移包",
                        "",
                        "Mac 默认安装路径：",
                        "  ~/Library/Application Support/Binggo/",
                        "",
                        "步骤：",
                        "1. 完全退出 Binggo.app",
                        "2. mkdir -p \"$HOME/Library/Application Support/Binggo\"",
                        "3. 解压本 zip，将其中的 config/ 与 data/ 复制进上述目录（覆盖）",
                        "4. 重新打开 Binggo.app（右键打开）",
                        "5. 打开 http://127.0.0.1:8181 确认账号、活动、监控名单与 LLM",
                        "",
                        json.dumps(manifest, ensure_ascii=False, indent=2),
                        "",
                    ]
                ),
                compress_type=zipfile.ZIP_DEFLATED,
            )
            zf.writestr(
                "migrate-manifest.json",
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            )
    finally:
        if tmp_db is not None and tmp_db.exists():
            tmp_db.unlink(missing_ok=True)

    return {
        "zip": str(out_zip),
        "size_bytes": out_zip.stat().st_size,
        **manifest,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="导出 Binggo 完整用户数据迁移包")
    parser.add_argument(
        "--source",
        type=Path,
        default=ROOT,
        help="主数据根（默认仓库根，含 data/binggo.db）",
    )
    parser.add_argument(
        "--appdata",
        type=Path,
        default=Path(os.environ.get("APPDATA", "")) / "Binggo"
        if os.environ.get("APPDATA")
        else None,
        help="可选：合并安装版 %%APPDATA%%\\Binggo 中缺失文件",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "dist" / "private" / "Binggo-userdata-migrate.zip",
        help="输出 zip 路径",
    )
    parser.add_argument(
        "--no-appdata",
        action="store_true",
        help="不合并 APPDATA",
    )
    args = parser.parse_args()
    appdata = None if args.no_appdata else args.appdata
    report = build_bundle(
        source_home=args.source.resolve(),
        appdata_home=appdata.resolve() if appdata else None,
        out_zip=args.out.resolve(),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
