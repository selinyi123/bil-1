"""合并六个数据源的活动链接，按动态 ID 去重后写入 merged_latest.json。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.merge_links import MERGED_OUTPUT_PATH, merge_activity_links, save_merged


def main() -> int:
    try:
        result = merge_activity_links()
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    out_path = save_merged(result)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    print(
        f"\n合并完成: {result.total_count} 条（去重 {result.duplicate_count} 条，新增 {result.new_count} 条）"
        f"\n已写入: {out_path}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
