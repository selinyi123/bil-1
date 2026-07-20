#!/usr/bin/env python3
"""将旧 JSON 数据全量导入 binggo.db，成功后归档到 data/backup/json_pre_sqlite/。

用法（仓库根目录）:
  python scripts/import_json_to_db.py
  python scripts/import_json_to_db.py --force
  python scripts/import_json_to_db.py --no-archive

退出码: 0 成功 / 2 非空未确认 / 3 源缺失损坏或校验失败 / 4 DB 错误
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.db.import_json import (  # noqa: E402
    EXIT_NONEMPTY,
    EXIT_OK,
    ImportError as JsonImportError,
    db_is_nonempty,
    run_import,
)
from src.db.import_json import _ensure_data_dirs  # noqa: E402
from src.db.schema import init_db  # noqa: E402


def _confirm_nonempty() -> bool:
    print(
        "警告：数据库已有业务数据。继续将按主键 upsert 覆盖；"
        "participation_actions 将按 uid 删除后重导。"
    )
    answer = input("确认继续？输入 yes 继续：").strip().lower()
    return answer == "yes"


def main() -> int:
    parser = argparse.ArgumentParser(description="导入旧 JSON 到 SQLite（零遗漏 + 归档）")
    parser.add_argument(
        "--force",
        action="store_true",
        help="非空库直接 upsert，跳过交互确认",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="与 --force 相同（兼容别名）",
    )
    parser.add_argument(
        "--no-archive",
        action="store_true",
        help="导入成功后不移动旧 JSON（调试用；正式迁移请勿使用）",
    )
    args = parser.parse_args()
    force = bool(args.force or args.yes)

    try:
        _ensure_data_dirs()
        init_db()
        if db_is_nonempty() and not force:
            if not sys.stdin.isatty() or not _confirm_nonempty():
                print("已取消：非空库未确认（需要 --force 或交互输入 yes）", file=sys.stderr)
                return EXIT_NONEMPTY
            force = True

        run_import(force=force, yes=True, archive=not args.no_archive)
    except JsonImportError as exc:
        print(f"导入失败: {exc}", file=sys.stderr)
        return int(exc.code)
    except Exception as exc:  # noqa: BLE001
        print(f"未预期错误: {exc}", file=sys.stderr)
        return 4
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
