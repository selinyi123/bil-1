"""对合并后的活动链接按 B 站 API 特征分类为转发/预约/互动抽奖。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.classify_links import CLASSIFIED_OUTPUT_PATH, classify_merged_links, save_classified


def main() -> int:
    parser = argparse.ArgumentParser(description="活动链接抽奖类型分类")
    parser.add_argument(
        "--force",
        action="store_true",
        help="忽略缓存，强制重新分类全部链接",
    )
    args = parser.parse_args()

    try:
        result = classify_merged_links(use_cache=not args.force, force=args.force)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    out_path = save_classified(result)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    print(
        f"\n分类完成: 转发 {result.counts['转发抽奖']} / "
        f"预约 {result.counts['预约抽奖']} / "
        f"互动 {result.counts['互动抽奖']}"
        f"\n新增分类: {result.new_count}"
        f"\n缓存命中: {result.cache_hits}"
        f"\n已写入: {out_path}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
