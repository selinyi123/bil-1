"""仅重试 rebuild_all_activity_details 失败的活动。"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.rebuild_all_activity_details import list_all_enrichable_tasks
from src.dead_links import DynamicDeletedError
from src.fetch_activity_info import (
    _all_enriched_activities,
    _build_result,
    _enrich_one,
    _load_existing_activities,
    save_enriched,
)
from src.lottery_classifier import LotteryType
from src.participation_store import load_participations
from src.status_refresh import refresh_local_activity_statuses

FAILURE_PATH = ROOT / "data" / "output" / "rebuild_all_failures.json"


def main() -> int:
    if not FAILURE_PATH.exists():
        print(json.dumps({"ok": True, "message": "无失败记录", "total": 0}, ensure_ascii=False))
        return 0

    failures = json.loads(FAILURE_PATH.read_text(encoding="utf-8"))
    task_map = dict(list_all_enrichable_tasks())
    tasks: list[tuple[str, LotteryType]] = []
    for item in failures:
        dynamic_id = str(item.get("dynamic_id") or "")
        lottery_type = task_map.get(dynamic_id) or item.get("lottery_type")
        if dynamic_id and lottery_type:
            tasks.append((dynamic_id, lottery_type))

    if not tasks:
        print(json.dumps({"ok": True, "message": "失败列表为空", "total": 0}, ensure_ascii=False))
        return 0

    existing_by_id = _load_existing_activities()
    participations = load_participations()

    enriched_at = int(time.time())
    newly_enriched: dict = {}
    ok = 0
    still_failed: list[dict[str, str]] = []

    print(f"重试 {len(tasks)} 条失败活动…", file=sys.stderr, flush=True)
    for index, (dynamic_id, lottery_type) in enumerate(tasks, start=1):
        try:
            activity = _enrich_one(dynamic_id, lottery_type, participation=participations.get(dynamic_id))
            newly_enriched[dynamic_id] = activity
            existing_by_id[dynamic_id] = activity.to_dict()
            ok += 1
        except DynamicDeletedError:
            existing_by_id.pop(dynamic_id, None)
            continue
        except Exception as exc:
            still_failed.append({"dynamic_id": dynamic_id, "lottery_type": lottery_type, "error": str(exc)})
            print(f"[{index}/{len(tasks)}] 仍失败 {dynamic_id}: {exc}", file=sys.stderr, flush=True)
            continue

        if index % 3 == 0 or index == len(tasks):
            merged = _all_enriched_activities(
                existing_by_id=existing_by_id,
                newly_enriched=newly_enriched,
                participations=participations,
            )
            save_enriched(
                _build_result(
                    merged,
                    enriched_at=enriched_at,
                    new_count=ok,
                    complete=index == len(tasks),
                    new_enriched_ids=sorted(newly_enriched.keys()),
                )
            )
        time.sleep(0.5)

    status = refresh_local_activity_statuses()
    summary = {"ok": len(still_failed) == 0, "retried": len(tasks), "succeeded": ok, "failed": len(still_failed), "status_refresh": status}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if still_failed:
        FAILURE_PATH.write_text(json.dumps(still_failed, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        FAILURE_PATH.unlink(missing_ok=True)
    return 0 if len(still_failed) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
