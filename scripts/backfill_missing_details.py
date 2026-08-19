"""一次性人工补全：为已分类但详情缺失的活动拉取完整详情（运维脚本，非用户功能）。"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.fetch_activity_info import (
    _all_enriched_activities,
    _build_result,
    _enrich_one,
    _load_existing_activities,
    list_missing_enrich_tasks,
    save_enriched,
)
from src.participation_store import load_participations


def main() -> int:
    tasks = list_missing_enrich_tasks()
    if not tasks:
        print(json.dumps({"ok": True, "message": "无缺失详情的活动", "total": 0}, ensure_ascii=False))
        return 0

    existing_by_id = _load_existing_activities()
    participations = load_participations()

    enriched_at = int(time.time())
    newly_enriched = {}
    ok = 0
    failed: list[dict[str, str]] = []

    print(f"待补全 {len(tasks)} 条活动详情…", file=sys.stderr, flush=True)
    for index, (dynamic_id, lottery_type) in enumerate(tasks, start=1):
        try:
            activity = _enrich_one(
                dynamic_id,
                lottery_type,
                participation=participations.get(dynamic_id),
            )
            if activity.skipped:
                raise RuntimeError("不应标记 skipped")
            newly_enriched[dynamic_id] = activity
            existing_by_id[dynamic_id] = activity.to_dict()
            ok += 1
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
        time.sleep(0.3)

    remaining = len(list_missing_enrich_tasks())
    summary = {
        "ok": remaining == 0,
        "attempted": len(tasks),
        "succeeded": ok,
        "failed": len(failed),
        "remaining": remaining,
        "failures": failed[:50],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if failed:
        fail_path = ROOT / "data" / "output" / "backfill_missing_failures.json"
        fail_path.write_text(json.dumps(failed, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"失败明细已写入: {fail_path}", file=sys.stderr)
    return 0 if remaining == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
