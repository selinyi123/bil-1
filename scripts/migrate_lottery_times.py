"""批量修正已保存活动中的开奖时间字段。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.fetch_activity_info import ENRICHED_OUTPUT_PATH
from src.lottery_time import is_standard_lottery_time_display, migrate_stored_lottery_times


def _count_bad_times(activities: list[dict]) -> int:
    bad = 0
    for item in activities:
        if not isinstance(item, dict):
            continue
        raw = str((item.get("conditions") or {}).get("lottery_time_text") or "")
        if raw and not is_standard_lottery_time_display(raw):
            bad += 1
    return bad


def main() -> int:
    if not ENRICHED_OUTPUT_PATH.exists():
        print("未找到 enriched_latest.json")
        return 1

    payload = json.loads(ENRICHED_OUTPUT_PATH.read_text(encoding="utf-8"))
    activities = [item for item in (payload.get("activities") or []) if isinstance(item, dict)]
    before = _count_bad_times(activities)

    migrated = migrate_stored_lottery_times(activities)
    payload["activities"] = activities
    ENRICHED_OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    after = _count_bad_times(activities)

    print(
        f"开奖时间迁移完成：修正 {migrated} 条，"
        f"非标准文本 {before} → {after}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
