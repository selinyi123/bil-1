"""全量重新抓取可参与活动的详情，并刷新活动状态（排除充电抽奖与已删除动态）。"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.activity_store import load_activities
from src.dead_links import DynamicDeletedError
from src.fetch_activity_info import (
    _all_enriched_activities,
    _build_result,
    _enrich_one,
    _load_existing_activities,
    save_enriched,
)
from src.lottery_classifier import PARTICIPATABLE_TYPES, LotteryType, is_charging_lottery_activity
from src.participation_store import load_participations
from src.status_refresh import refresh_local_activity_statuses


def list_all_enrichable_tasks() -> list[tuple[str, LotteryType]]:
    tasks: list[tuple[str, LotteryType]] = []
    for item in load_activities():
        dynamic_id = str(item.get("dynamic_id") or "")
        lottery_type = item.get("lottery_type")
        if not dynamic_id or is_charging_lottery_activity(item):
            continue
        if lottery_type not in PARTICIPATABLE_TYPES:
            continue
        tasks.append((dynamic_id, lottery_type))
    return tasks


def main() -> int:
    tasks = list_all_enrichable_tasks()
    if not tasks:
        print(json.dumps({"ok": True, "message": "无可参与的活动", "total": 0}, ensure_ascii=False))
        return 0

    existing_by_id = _load_existing_activities()
    participations = load_participations()

    enriched_at = int(time.time())
    newly_enriched: dict = {}
    ok = 0
    skipped_deleted = 0
    failed: list[dict[str, str]] = []

    print(f"全量重抓 {len(tasks)} 条活动详情…", file=sys.stderr, flush=True)
    for index, (dynamic_id, lottery_type) in enumerate(tasks, start=1):
        try:
            activity = _enrich_one(
                dynamic_id,
                lottery_type,
                participation=participations.get(dynamic_id),
            )
            newly_enriched[dynamic_id] = activity
            existing_by_id[dynamic_id] = activity.to_dict()
            ok += 1
        except DynamicDeletedError:
            skipped_deleted += 1
            existing_by_id.pop(dynamic_id, None)
            print(f"[{index}/{len(tasks)}] 已删除 {dynamic_id}", file=sys.stderr, flush=True)
            continue
        except Exception as exc:
            failed.append(
                {
                    "dynamic_id": dynamic_id,
                    "lottery_type": lottery_type,
                    "error": str(exc),
                }
            )
            print(f"[{index}/{len(tasks)}] 失败 {dynamic_id}: {exc}", file=sys.stderr, flush=True)
            continue

        if index % 5 == 0 or index == len(tasks):
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
            print(f"[{index}/{len(tasks)}] 已成功 {ok} 条", file=sys.stderr, flush=True)
        time.sleep(0.35)

    status = refresh_local_activity_statuses()
    summary = {
        "ok": len(failed) == 0,
        "attempted": len(tasks),
        "succeeded": ok,
        "deleted_skipped": skipped_deleted,
        "failed": len(failed),
        "failures": failed[:80],
        "status_refresh": status,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if failed:
        fail_path = ROOT / "data" / "output" / "rebuild_all_failures.json"
        fail_path.write_text(json.dumps(failed, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"失败明细已写入: {fail_path}", file=sys.stderr)
    return 0 if len(failed) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
