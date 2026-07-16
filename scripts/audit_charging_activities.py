"""审查本地活动数据中的充电抽奖（business_type=12 / 充电抽奖）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.fetch_activity_info import ENRICHED_OUTPUT_PATH
from src.lottery_classifier import is_charging_lottery_activity, migrate_stored_charging_lotteries
from web.activity_service import invalidate_activity_cache, list_activities


def main() -> int:
    if not ENRICHED_OUTPUT_PATH.exists():
        print("未找到 enriched_latest.json")
        return 1

    payload = json.loads(ENRICHED_OUTPUT_PATH.read_text(encoding="utf-8"))
    activities = [item for item in (payload.get("activities") or []) if isinstance(item, dict)]

    before = [item for item in activities if is_charging_lottery_activity(item)]
    print(f"审查 {len(activities)} 条本地活动，发现充电抽奖 {len(before)} 条：")
    for item in before:
        print(
            f"  - {item.get('dynamic_id')} "
            f"type={item.get('lottery_type')} "
            f"business_type={item.get('business_type')} "
            f"skipped={item.get('skipped')}"
        )

    migrated = migrate_stored_charging_lotteries(activities)
    payload["activities"] = activities
    ENRICHED_OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    invalidate_activity_cache()

    after_payload = json.loads(ENRICHED_OUTPUT_PATH.read_text(encoding="utf-8"))
    after = [
        item
        for item in (after_payload.get("activities") or [])
        if isinstance(item, dict) and is_charging_lottery_activity(item)
    ]
    listed = list_activities(page=1, page_size=1000)
    listed_ids = {item.get("dynamic_id") for item in listed.get("items") or []}
    leaked = [item for item in after if str(item.get("dynamic_id")) in listed_ids]

    print(
        f"\n修正完成：标记跳过 {migrated} 条；"
        f"活动列表中仍可见的充电抽奖 {len(leaked)} 条"
    )
    if leaked:
        for item in leaked:
            print(f"  ! 仍可见: {item.get('dynamic_id')}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
