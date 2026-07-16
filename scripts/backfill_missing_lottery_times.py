"""为本地缺失开奖时间的活动补全推断时间（参奖/入库后半年）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.fetch_activity_info import ENRICHED_OUTPUT_PATH
from src.status_refresh import backfill_missing_lottery_times, refresh_local_activity_statuses


def main() -> int:
    if not ENRICHED_OUTPUT_PATH.exists():
        print("未找到 enriched_latest.json")
        return 1

    backfill = backfill_missing_lottery_times(path=ENRICHED_OUTPUT_PATH)
    refresh = refresh_local_activity_statuses(path=ENRICHED_OUTPUT_PATH)
    print(
        json.dumps(
            {
                "backfill": backfill,
                "refresh": refresh,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
