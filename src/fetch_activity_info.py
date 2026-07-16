from __future__ import annotations

import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from src.bilibili_client import BilibiliClient
from src.dead_links import DynamicDeletedError, is_dynamic_deleted, purge_dynamic_ids
from src.activity_store import (
    ACTIVITIES_OUTPUT_PATH,
    load_activities,
    load_payload,
    replace_all_activities,
    update_activity,
)
from src.state_store import DATA_DIR

ENRICHED_OUTPUT_PATH = ACTIVITIES_OUTPUT_PATH
from src.lottery_enricher import (
    EnrichedActivity,
    activity_from_cache,
    apply_p2_to_activity,
    enrich_activity,
)
from src.lottery_classifier import (
    LotteryType,
    PARTICIPATABLE_TYPES,
    migrate_stored_charging_lotteries,
)
from src.participation_store import ParticipationRecord, load_participations
from src.lottery_time import migrate_stored_lottery_times
from src.sources.common import load_previous_output
from src.state_store import DATA_DIR
from src.app_logging import get_logger

logger = get_logger("fetch")

DEFAULT_WORKERS = 4
DEFAULT_SAVE_EVERY = 5
ENRICH_RETRY_ATTEMPTS = 3
EnrichProgressCallback = Callable[[int, int, str], None]


@dataclass
class EnrichResult:
    enriched_at: int
    total_count: int
    new_count: int
    p1_count: int
    skipped_count: int
    counts: dict[str, int]
    user_status_counts: dict[str, int]
    activities: list[dict]
    new_enriched_ids: list[str] = field(default_factory=list)
    complete: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


def _build_draw_counts(activities: list[EnrichedActivity]) -> dict[str, int]:
    counts = {"active": 0, "ended": 0, "skipped": 0}
    for activity in activities:
        if activity.skipped:
            counts["skipped"] += 1
        elif activity.draw_status == "ended":
            counts["ended"] += 1
        else:
            counts["active"] += 1
    return counts


def _build_user_status_counts(activities: list[EnrichedActivity]) -> dict[str, int]:
    counts = {"已结束": 0, "已参加": 0, "未参加": 0}
    for activity in activities:
        counts[activity.activity_status] += 1
    return counts


def _load_existing_activities() -> dict[str, dict]:
    return {
        str(item.get("dynamic_id")): item
        for item in load_activities()
        if item.get("dynamic_id")
    }


def count_pending_enrich() -> int:
    return len(list_missing_enrich_tasks())


def count_skipped_pending_retry() -> int:
    return 0


def is_enriched_complete(cached: dict | None) -> bool:
    if not cached:
        return False
    if cached.get("skipped"):
        return cached.get("lottery_type") == "充电抽奖"
    if not cached.get("lottery_time"):
        return False
    if not cached.get("prizes"):
        return False
    if not cached.get("repost_fetched"):
        return False
    return True


def list_missing_enrich_tasks() -> list[tuple[str, LotteryType]]:
    """列出本地活动中详情不完整、需补全的可参与活动。"""
    existing = _load_existing_activities()
    tasks: list[tuple[str, LotteryType]] = []
    for dynamic_id, cached in existing.items():
        lottery_type = cached.get("lottery_type")
        if lottery_type == "充电抽奖" or lottery_type not in PARTICIPATABLE_TYPES:
            continue
        if is_enriched_complete(cached):
            continue
        tasks.append((dynamic_id, lottery_type))
    return tasks


def _restore_existing_activity(
    *,
    dynamic_id: str,
    lottery_type: LotteryType,
    cached: dict,
    participation: ParticipationRecord | None,
) -> EnrichedActivity | None:
    restored = activity_from_cache(dynamic_id, lottery_type, cached)
    if restored:
        return apply_p2_to_activity(restored, participation=participation)
    cached_type = cached.get("lottery_type")
    if cached_type and cached_type != lottery_type:
        restored = activity_from_cache(dynamic_id, cached_type, cached)
        if restored:
            return apply_p2_to_activity(restored, participation=participation)
    return None


def _all_enriched_activities(
    *,
    existing_by_id: dict[str, dict],
    newly_enriched: dict[str, EnrichedActivity],
    participations: dict[str, ParticipationRecord],
) -> list[EnrichedActivity]:
    activities: list[EnrichedActivity] = []
    seen: set[str] = set()
    for dynamic_id, cached in existing_by_id.items():
        seen.add(dynamic_id)
        if dynamic_id in newly_enriched:
            activities.append(newly_enriched[dynamic_id])
            continue
        lottery_type = cached.get("lottery_type")
        if lottery_type not in PARTICIPATABLE_TYPES:
            continue
        restored = _restore_existing_activity(
            dynamic_id=dynamic_id,
            lottery_type=lottery_type,
            cached=cached,
            participation=participations.get(dynamic_id),
        )
        if restored:
            activities.append(restored)
    for dynamic_id, activity in newly_enriched.items():
        if dynamic_id not in seen:
            activities.append(activity)
    return sorted(activities, key=lambda entry: entry.dynamic_id)


def _build_result(
    activities: list[EnrichedActivity],
    *,
    enriched_at: int,
    new_count: int,
    complete: bool,
    new_enriched_ids: list[str] | None = None,
) -> EnrichResult:
    ordered = sorted(activities, key=lambda entry: entry.dynamic_id)
    return EnrichResult(
        enriched_at=enriched_at,
        total_count=len(ordered),
        new_count=new_count,
        p1_count=sum(1 for entry in ordered if not entry.skipped),
        skipped_count=sum(1 for entry in ordered if entry.skipped),
        counts=_build_draw_counts(ordered),
        user_status_counts=_build_user_status_counts(ordered),
        activities=[entry.to_dict() for entry in ordered],
        new_enriched_ids=sorted(new_enriched_ids or []),
        complete=complete,
    )


def _enrich_one(
    dynamic_id: str,
    lottery_type: LotteryType,
    *,
    participation: ParticipationRecord | None,
) -> EnrichedActivity:
    last_error: Exception | None = None
    for attempt in range(ENRICH_RETRY_ATTEMPTS):
        try:
            with BilibiliClient() as client:
                if is_dynamic_deleted(client, dynamic_id):
                    purge_dynamic_ids([dynamic_id])
                    raise DynamicDeletedError(dynamic_id)
                return enrich_activity(
                    client,
                    dynamic_id=dynamic_id,
                    lottery_type=lottery_type,
                    participation=participation,
                )
        except DynamicDeletedError:
            raise
        except Exception as exc:
            last_error = exc
            if attempt < ENRICH_RETRY_ATTEMPTS - 1:
                time.sleep(1.2 * (attempt + 1))
                continue
            raise
    if last_error:
        raise last_error
    raise RuntimeError(f"活动 {dynamic_id} 拉取失败")


def load_cached_enrich_result() -> EnrichResult:
    payload = load_payload()
    participations = load_participations()
    existing_by_id = _load_existing_activities()
    merged = _all_enriched_activities(
        existing_by_id=existing_by_id,
        newly_enriched={},
        participations=participations,
    )
    enriched_at = int(payload.get("updated_at") or time.time())
    return _build_result(
        merged,
        enriched_at=enriched_at,
        new_count=0,
        complete=True,
        new_enriched_ids=[],
    )


def fetch_activity_info(
    *,
    workers: int = DEFAULT_WORKERS,
    save_every: int = DEFAULT_SAVE_EVERY,
    on_progress: EnrichProgressCallback | None = None,
    continue_on_error: bool = False,
) -> EnrichResult:
    """补全本地活动中详情不完整的记录。"""
    existing_by_id = _load_existing_activities()
    participations = load_participations()
    reset_detail_api_state()
    enriched_at = int(time.time())
    tasks = list_missing_enrich_tasks()

    if not tasks:
        return load_cached_enrich_result()

    newly_enriched: dict[str, EnrichedActivity] = {}
    activities_lock = threading.Lock()
    processed = 0
    failed: list[dict[str, str]] = []
    total = len(tasks)
    initial_existing_ids = set(existing_by_id.keys())

    def _current_new_enriched_ids() -> list[str]:
        return sorted(did for did in newly_enriched if did not in initial_existing_ids)

    def flush_partial(*, complete: bool) -> None:
        with activities_lock:
            merged = _all_enriched_activities(
                existing_by_id=existing_by_id,
                newly_enriched=newly_enriched,
                participations=participations,
            )
            save_enriched(
                _build_result(
                    merged,
                    enriched_at=enriched_at,
                    new_count=len(_current_new_enriched_ids()),
                    complete=complete,
                    new_enriched_ids=_current_new_enriched_ids(),
                )
            )

    if on_progress:
        on_progress(0, total, f"正在拉取 {total} 条活动详情")

    worker_count = max(1, workers)
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(
                _enrich_one,
                dynamic_id,
                lottery_type,
                participation=participations.get(dynamic_id),
            ): dynamic_id
            for dynamic_id, lottery_type in tasks
        }

        for future in as_completed(futures):
            dynamic_id = futures[future]
            try:
                activity = future.result()
            except DynamicDeletedError:
                if continue_on_error:
                    with activities_lock:
                        failed.append({"dynamic_id": dynamic_id, "error": "动态已删除"})
                        existing_by_id.pop(dynamic_id, None)
                    continue
                raise
            except Exception as exc:
                if continue_on_error:
                    with activities_lock:
                        failed.append({"dynamic_id": dynamic_id, "error": str(exc)})
                    logger.warning("活动 %s 详情拉取失败（已跳过）: %s", dynamic_id, exc)
                    continue
                raise
            if activity.skipped:
                raise RuntimeError(
                    f"活动 {dynamic_id} 被标记 skipped，仅允许充电抽奖使用 skipped"
                )
            with activities_lock:
                newly_enriched[activity.dynamic_id] = activity
                existing_by_id[activity.dynamic_id] = activity.to_dict()
                processed += 1
                if on_progress and (processed % 5 == 0 or processed == total):
                    on_progress(processed, total, f"正在拉取活动详情 ({processed}/{total})")
                if processed % 10 == 0 or processed == total:
                    logger.info("详情拉取进度: %s/%s", processed, total)
                should_flush = save_every > 0 and processed % save_every == 0
            if should_flush:
                flush_partial(complete=False)

    if processed > 0 and save_every > 0 and processed % save_every != 0:
        flush_partial(complete=True)

    merged = _all_enriched_activities(
        existing_by_id=existing_by_id,
        newly_enriched=newly_enriched,
        participations=participations,
    )
    new_enriched_ids = _current_new_enriched_ids()
    return _build_result(
        merged,
        enriched_at=enriched_at,
        new_count=len(new_enriched_ids),
        complete=True,
        new_enriched_ids=new_enriched_ids,
    )


def mark_enriched_joined(dynamic_id: str) -> Path | None:
    dynamic_id = str(dynamic_id or "").strip()
    if not dynamic_id:
        return None
    payload = load_payload()
    activities = [item for item in (payload.get("activities") or []) if isinstance(item, dict)]
    target: dict | None = None
    for item in activities:
        if str(item.get("dynamic_id") or "") == dynamic_id:
            target = dict(item)
            break
    if not target:
        return None
    target["activity_status"] = "已参加"
    target["draw_tag"] = ""
    target["status_classified"] = True
    if target.get("platform_participated") is not None:
        target["platform_participated"] = True
    update_activity(dynamic_id, target)
    return ENRICHED_OUTPUT_PATH


def save_enriched(result: EnrichResult) -> Path:
    activities = list(result.activities)
    migrated_times = migrate_stored_lottery_times(activities)
    migrated_charging = migrate_stored_charging_lotteries(activities)
    if migrated_times:
        logger.info("开奖时间已规范化 %s 条", migrated_times)
    if migrated_charging:
        logger.info("充电抽奖已标记跳过 %s 条", migrated_charging)
    filtered = [
        item
        for item in activities
        if isinstance(item, dict)
        and not item.get("skipped")
        and item.get("lottery_type") != "充电抽奖"
    ]
    replace_all_activities(filtered)
    return ENRICHED_OUTPUT_PATH
