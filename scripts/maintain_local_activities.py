"""治理本地活动库：删除充电/失效链接，补全缺失详情。"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.activity_store import load_activities, replace_all_activities
from src.bilibili_client import BilibiliClient
from src.dead_links import is_dynamic_deleted, partition_alive_dynamic_ids, purge_dynamic_ids
from src.fetch_activity_info import is_enriched_complete
from src.lottery_classifier import is_charging_lottery_activity, PARTICIPATABLE_TYPES
from src.lottery_enricher import enrich_activity
from src.participation_store import load_participations
from src.pipeline.status_step import apply_initial_status


def _needs_enrich(item: dict) -> bool:
    lottery_type = item.get("lottery_type")
    if lottery_type not in PARTICIPATABLE_TYPES:
        return False
    return not is_enriched_complete(item)


def _enrich_one(
    dynamic_id: str,
    lottery_type: str,
    participation,
) -> dict:
    with BilibiliClient() as client:
        if is_dynamic_deleted(client, dynamic_id):
            raise RuntimeError(f"dead:{dynamic_id}")
        activity = enrich_activity(
            client,
            dynamic_id=dynamic_id,
            lottery_type=lottery_type,
            participation=participation,
        )
        if activity.skipped:
            raise RuntimeError(f"skipped:{dynamic_id}")
        row = apply_initial_status(activity.to_dict())
        return row


def main() -> int:
    parser = argparse.ArgumentParser(description="治理本地活动库")
    parser.add_argument("--workers", type=int, default=4, help="详情补全并发数")
    parser.add_argument("--skip-enrich", action="store_true", help="仅删除，不补全详情")
    parser.add_argument("--dry-run", action="store_true", help="只统计，不写回")
    args = parser.parse_args()

    activities = load_activities()
    participations = load_participations()
    summary: dict = {
        "started_at": int(time.time()),
        "initial_count": len(activities),
        "removed_charging": 0,
        "removed_dead": 0,
        "enriched": 0,
        "enrich_failed": [],
        "final_count": 0,
        "dry_run": args.dry_run,
    }

    kept: list[dict] = []
    charging_ids: list[str] = []
    for item in activities:
        if is_charging_lottery_activity(item) or item.get("lottery_type") == "充电抽奖":
            charging_ids.append(str(item.get("dynamic_id") or ""))
            continue
        if item.get("skipped"):
            charging_ids.append(str(item.get("dynamic_id") or ""))
            continue
        kept.append(dict(item))

    summary["removed_charging"] = len(charging_ids)

    alive_ids = [str(item.get("dynamic_id") or "") for item in kept if item.get("dynamic_id")]
    dead_ids: list[str] = []
    if alive_ids:
        print(f"检测 {len(alive_ids)} 条链接是否失效…", file=sys.stderr, flush=True)
        with BilibiliClient() as client:
            _, dead_ids = partition_alive_dynamic_ids(client, alive_ids)

    if dead_ids:
        summary["removed_dead"] = len(dead_ids)
        dead_set = set(dead_ids)
        kept = [item for item in kept if str(item.get("dynamic_id") or "") not in dead_set]

    tasks = [
        (str(item.get("dynamic_id")), str(item.get("lottery_type")))
        for item in kept
        if _needs_enrich(item)
    ]
    print(
        f"待补全详情 {len(tasks)} 条（充电/跳过 {summary['removed_charging']}，失效 {summary['removed_dead']}）",
        file=sys.stderr,
        flush=True,
    )

    if tasks and not args.skip_enrich:
        by_id = {str(item.get("dynamic_id")): item for item in kept}
        workers = max(1, min(args.workers, len(tasks)))

        def _run(task: tuple[str, str]) -> tuple[str, dict | None, str | None]:
            dynamic_id, lottery_type = task
            try:
                row = _enrich_one(
                    dynamic_id,
                    lottery_type,
                    participations.get(dynamic_id),
                )
                prior = by_id.get(dynamic_id) or {}
                for key in ("activity_status", "draw_tag", "platform_participated", "status_classified"):
                    if key in prior and prior.get(key) not in (None, ""):
                        row[key] = prior[key]
                return dynamic_id, row, None
            except Exception as exc:
                return dynamic_id, None, str(exc)

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_run, task): task for task in tasks}
            done = 0
            for future in as_completed(futures):
                dynamic_id, row, error = future.result()
                done += 1
                if row:
                    by_id[dynamic_id] = row
                    summary["enriched"] += 1
                elif error:
                    if error.startswith("dead:"):
                        dead_ids.append(dynamic_id)
                        by_id.pop(dynamic_id, None)
                        summary["removed_dead"] += 1
                    else:
                        summary["enrich_failed"].append({"dynamic_id": dynamic_id, "error": error})
                if done % 10 == 0 or done == len(tasks):
                    print(f"补全进度 {done}/{len(tasks)}", file=sys.stderr, flush=True)

        kept = list(by_id.values())

    summary["final_count"] = len(kept)
    summary["finished_at"] = int(time.time())

    if args.dry_run:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    replace_all_activities(kept)
    if charging_ids or dead_ids:
        purge_dynamic_ids([*charging_ids, *dead_ids])

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not summary["enrich_failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
