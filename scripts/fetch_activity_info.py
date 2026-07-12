"""拉取抽奖活动信息（P1+P2+P3）。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.fetch_activity_info import ENRICHED_OUTPUT_PATH, fetch_activity_info, save_enriched


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, OSError, ValueError):
            pass

    parser = argparse.ArgumentParser(description="抽奖活动信息拉取（P1）")
    parser.add_argument(
        "--force",
        action="store_true",
        help="忽略已结束活动缓存，强制重新拉取",
    )
    args = parser.parse_args()

    try:
        result = fetch_activity_info(use_cache=not args.force, force=args.force)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    out_path = save_enriched(result)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    print(
        f"\n信息拉取完成: P1 {result.p1_count} / 跳过 {result.skipped_count}"
        f"\n进行中 {result.counts['active']} / 已结束 {result.counts['ended']}"
        f"\n新增拉取: {result.new_count}"
        f"\n缓存命中: {result.cache_hits}"
        f"\n已写入: {out_path}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
