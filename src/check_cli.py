from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

from src.sources.common import CheckResult


def run_check(
    *,
    description: str,
    force_help: str,
    no_update_label: str,
    check_update: Callable[..., CheckResult],
    save_result: Callable[[CheckResult], Path | None],
    output_path: Path,
) -> int:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--force", action="store_true", help=force_help)
    args = parser.parse_args()

    try:
        result = check_update(force=args.force)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))

    out_path = save_result(result)
    if out_path:
        print(f"\n结果已写入: {out_path}", file=sys.stderr)
        print(f"检测到更新，共提取 {len(result.activity_links)} 条活动链接。", file=sys.stderr)
    else:
        print(f"\n{no_update_label}，跳过链接提取，保留已有结果: {output_path}", file=sys.stderr)

    return 0
