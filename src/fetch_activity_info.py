from __future__ import annotations

import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from typing import Callable

from src.bilibili_client import BilibiliClient
from src.classify_links import CLASSIFIED_OUTPUT_PATH
from src.enrich_cache import get_cached_entry, merge_cache, remove_cache_entries
from src.lottery_api import extract_activity_heat, fetch_dynamic_detail, reset_detail_api_state
from src.lottery_enricher import (
    EnrichedActivity,
    activity_from_cache,
    apply_p2_to_activity,
    enrich_activity,
    enrich_forward_activity,
)
from src.lottery_classifier import CLASSIFIABLE_TYPES, LotteryType, PARTICIPATABLE_TYPES
from src.participation_store import ParticipationRecord, load_participations
from src.lottery_classifier import migrate_stored_charging_lotteries
from src.lottery_time import migrate_stored_lottery_times
from src.sources.common import load_previous_output
from src.state_store import DATA_DIR
from src.app_logging import get_logger

logger = get_logger("fetch")

ENRICHED_OUTPUT_PATH = DATA_DIR / "output" / "enriched_latest.json"
DEFAULT_WORKERS = 12
DEFAULT_HEAT_WORKERS = 6
DEFAULT_SAVE_EVERY = 10
ENRICH_RETRY_ATTEMPTS = 3
EnrichProgressCallback = Callable[[int, int, str], None]


@dataclass
class EnrichResult:
    enriched_at: int
    total_count: int
    new_count: int
    p1_count: int
    skipped_count: int
    cache_hits: int
    counts: dict[str, int]
    user_status_counts: dict[str, int]
    activities: list[dict]
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


def _cache_missing_repost_count(cached: dict) -> bool:
    lottery_type = cached.get("lottery_type")
    if lottery_type == "预约抽奖" and not cached.get("heat_from_reserve"):
        return True
    if not cached.get("repost_fetched"):
        return True
    if int(cached.get("repost_count") or 0) == 0 and not cached.get("repost_zero_confirmed"):
        return True
    return False


def _should_use_cache(cached: dict, *, force: bool) -> bool:
    if force:
        return False
    if cached.get("skipped"):
        return False
    if _cache_missing_repost_count(cached):
        return False
    return cached.get("draw_status") == "ended"


def count_missing_repost(existing_by_id: dict[str, dict]) -> int:
    return sum(1 for item in existing_by_id.values() if _cache_missing_repost_count(item))


def count_pending_heat_backfill() -> int:
    """已有活动但尚未确认热度（转发数）的数量。"""
    existing = _load_existing_activities()
    count = 0
    for cached in existing.values():
        lottery_type = cached.get("lottery_type")
        if lottery_type not in PARTICIPATABLE_TYPES:
            continue
        if _cache_missing_repost_count(cached):
            count += 1
    return count


def load_existing_activity_map() -> dict[str, dict]:
    return _load_existing_activities()


def _fetch_repost_count(dynamic_id: str, lottery_type: LotteryType) -> tuple[int, bool, bool]:
    """返回 (热度, 是否成功, 是否来自预约人数)。"""
    with BilibiliClient() as client:
        item = fetch_dynamic_detail(client, dynamic_id)
        if not item:
            return 0, False, False
        heat, from_reserve = extract_activity_heat(item, lottery_type=lottery_type)
        return heat, True, from_reserve


def _backfill_repost_one(
    dynamic_id: str,
    lottery_type: LotteryType,
    existing: dict,
    *,
    participation: ParticipationRecord | None,
) -> EnrichedActivity | None:
    last_error: Exception | None = None
    for attempt in range(ENRICH_RETRY_ATTEMPTS):
        try:
            repost, ok, from_reserve = _fetch_repost_count(dynamic_id, lottery_type)
            if not ok:
                return None
            restored = _restore_existing_activity(
                dynamic_id=dynamic_id,
                lottery_type=lottery_type,
                cached=existing,
                participation=participation,
            )
            if not restored:
                return None
            return replace(
                restored,
                repost_count=repost,
                repost_fetched=True,
                repost_zero_confirmed=repost == 0,
                heat_from_reserve=from_reserve,
                enriched_at=int(time.time()),
            )
        except Exception as exc:
            last_error = exc
            if attempt < ENRICH_RETRY_ATTEMPTS - 1:
                time.sleep(0.8 * (attempt + 1))
                continue
            raise
    if last_error:
        raise last_error
    return None


def _reset_stale_heat_flags(existing_by_id: dict[str, dict]) -> int:
    """清除错误的热度拉取标记，便于重新补全。"""
    reset = 0
    for cached in existing_by_id.values():
        if (
            int(cached.get("repost_count") or 0) == 0
            and cached.get("repost_fetched")
            and not cached.get("repost_zero_confirmed")
        ):
            cached["repost_fetched"] = False
            reset += 1
    return reset


def backfill_repost_counts(
    *,
    workers: int = DEFAULT_WORKERS,
    save_every: int = DEFAULT_SAVE_EVERY,
    on_progress: EnrichProgressCallback | None = None,
) -> dict[str, int]:
    """仅补全已有活动的转发数（热度），不重新拉取完整详情。"""
    existing_by_id = _load_existing_activities()
    stale_reset = _reset_stale_heat_flags(existing_by_id)
    if stale_reset:
        logger.info("重置 %s 条错误热度标记", stale_reset)
    classified = load_previous_output(CLASSIFIED_OUTPUT_PATH) or {}
    classified_items = classified.get("activities") or []
    participations = load_participations()
    reset_detail_api_state()

    tasks: list[tuple[str, LotteryType, dict]] = []
    for dynamic_id, cached in existing_by_id.items():
        lottery_type = cached.get("lottery_type")
        if lottery_type not in PARTICIPATABLE_TYPES:
            continue
        if _cache_missing_repost_count(cached):
            tasks.append((dynamic_id, lottery_type, cached))

    total = len(tasks)
    if total == 0:
        if on_progress:
            on_progress(0, 0, "热度数据已是最新")
        return {"updated": 0, "total": len(existing_by_id), "failed": 0}

    if on_progress:
        on_progress(0, total, f"正在补全 {total} 条活动热度")

    enriched_at = int(time.time())
    newly_enriched: dict[str, EnrichedActivity] = {}
    activities_lock = threading.Lock()
    processed = 0
    failed = 0

    def flush_partial(*, complete: bool) -> None:
        with activities_lock:
            merged = _merge_activities(
                classified_items,
                existing_by_id=existing_by_id,
                newly_enriched=newly_enriched,
                participations=participations,
            )
            save_enriched(
                _build_result(
                    merged,
                    enriched_at=enriched_at,
                    cache_hits=0,
                    new_count=len(newly_enriched),
                    complete=complete,
                )
            )

    worker_count = max(1, workers)
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(
                _backfill_repost_one,
                dynamic_id,
                lottery_type,
                existing,
                participation=participations.get(dynamic_id),
            ): dynamic_id
            for dynamic_id, lottery_type, existing in tasks
        }
        for future in as_completed(futures):
            dynamic_id = futures[future]
            try:
                activity = future.result()
            except Exception as exc:
                failed += 1
                logger.warning("热度补全失败 %s: %s", dynamic_id, exc)
                continue
            if activity:
                with activities_lock:
                    newly_enriched[activity.dynamic_id] = activity
            processed += 1
            if on_progress and (processed % 10 == 0 or processed == total):
                on_progress(processed, total, f"正在补全活动热度 ({processed}/{total})")
            if save_every > 0 and processed % save_every == 0:
                flush_partial(complete=False)

    flush_partial(complete=True)
    if on_progress:
        on_progress(total, total, f"热度补全完成，更新 {len(newly_enriched)} 条")
    return {
        "updated": len(newly_enriched),
        "total": len(existing_by_id),
        "failed": failed,
    }


def _enrich_one(
    dynamic_id: str,
    lottery_type: LotteryType,
    *,
    use_cache: bool,
    participation: ParticipationRecord | None,
) -> EnrichedActivity:
    last_error: Exception | None = None
    for attempt in range(ENRICH_RETRY_ATTEMPTS):
        try:
            if use_cache:
                cached = get_cached_entry(dynamic_id)
                if cached and _should_use_cache(cached, force=False):
                    restored = activity_from_cache(dynamic_id, lottery_type, cached)
                    if restored:
                        return apply_p2_to_activity(restored, participation=participation)

            with BilibiliClient() as client:
                if lottery_type == "转发抽奖":
                    return enrich_forward_activity(
                        client,
                        dynamic_id=dynamic_id,
                        participation=participation,
                    )
                return enrich_activity(
                    client,
                    dynamic_id=dynamic_id,
                    lottery_type=lottery_type,
                    participation=participation,
                )
        except Exception as exc:
            last_error = exc
            if attempt < ENRICH_RETRY_ATTEMPTS - 1:
                time.sleep(1.2 * (attempt + 1))
                continue
            raise
    if last_error:
        raise last_error
    raise RuntimeError(f"活动 {dynamic_id} 拉取失败")


def _build_result(
    activities: list[EnrichedActivity],
    *,
    enriched_at: int,
    cache_hits: int,
    new_count: int,
    complete: bool,
) -> EnrichResult:
    ordered = sorted(activities, key=lambda entry: entry.dynamic_id)
    return EnrichResult(
        enriched_at=enriched_at,
        total_count=len(ordered),
        new_count=new_count,
        p1_count=sum(1 for entry in ordered if not entry.skipped),
        skipped_count=sum(1 for entry in ordered if entry.skipped),
        cache_hits=cache_hits,
        counts=_build_draw_counts(ordered),
        user_status_counts=_build_user_status_counts(ordered),
        activities=[entry.to_dict() for entry in ordered],
        complete=complete,
    )


def _load_existing_activities() -> dict[str, dict]:
    payload = load_previous_output(ENRICHED_OUTPUT_PATH) or {}
    return {
        str(item.get("dynamic_id")): item
        for item in (payload.get("activities") or [])
        if isinstance(item, dict) and item.get("dynamic_id")
    }


def _restore_existing_activity(
    *,
    dynamic_id: str,
    lottery_type: LotteryType,
    cached: dict,
    participation: ParticipationRecord | None,
) -> EnrichedActivity | None:
    restored = activity_from_cache(dynamic_id, lottery_type, cached)
    if not restored:
        return None
    return apply_p2_to_activity(restored, participation=participation)


def _merge_activities(
    classified_items: list[dict],
    *,
    existing_by_id: dict[str, dict],
    newly_enriched: dict[str, EnrichedActivity],
    participations: dict[str, ParticipationRecord],
) -> list[EnrichedActivity]:
    activities: list[EnrichedActivity] = []
    seen: set[str] = set()
    for item in classified_items:
        dynamic_id = str(item.get("dynamic_id") or "")
        lottery_type = item.get("lottery_type")
        if not dynamic_id or lottery_type not in CLASSIFIABLE_TYPES:
            continue
        seen.add(dynamic_id)

        if dynamic_id in newly_enriched:
            activities.append(newly_enriched[dynamic_id])
            continue

        cached = existing_by_id.get(dynamic_id)
        if cached:
            restored = _restore_existing_activity(
                dynamic_id=dynamic_id,
                lottery_type=lottery_type,
                cached=cached,
                participation=participations.get(dynamic_id),
            )
            if restored:
                activities.append(restored)

    for dynamic_id, cached in existing_by_id.items():
        if dynamic_id in seen:
            continue
        lottery_type = cached.get("lottery_type")
        if lottery_type not in ("转发抽奖", "预约抽奖", "互动抽奖"):
            continue
        restored = _restore_existing_activity(
            dynamic_id=dynamic_id,
            lottery_type=lottery_type,
            cached=cached,
            participation=participations.get(dynamic_id),
        )
        if restored:
            activities.append(restored)
    return sorted(activities, key=lambda entry: entry.dynamic_id)


def count_pending_enrich() -> int:
    """已分类但尚未写入 enriched 的活动数量。"""
    classified = load_previous_output(CLASSIFIED_OUTPUT_PATH) or {}
    existing = _load_existing_activities()
    count = 0
    for item in classified.get("activities") or []:
        if not isinstance(item, dict):
            continue
        dynamic_id = str(item.get("dynamic_id") or "")
        lottery_type = item.get("lottery_type")
        if not dynamic_id or lottery_type not in CLASSIFIABLE_TYPES:
            continue
        if dynamic_id not in existing:
            count += 1
    return count


def load_cached_enrich_result() -> EnrichResult:
    """从本地 enriched_latest.json 加载，不发起网络请求。"""
    payload = load_previous_output(ENRICHED_OUTPUT_PATH) or {}
    activities_raw = payload.get("activities") or []
    participations = load_participations()
    activities: list[EnrichedActivity] = []
    for item in activities_raw:
        if not isinstance(item, dict):
            continue
        dynamic_id = str(item.get("dynamic_id") or "")
        lottery_type = item.get("lottery_type")
        if not dynamic_id or lottery_type not in CLASSIFIABLE_TYPES:
            continue
        restored = activity_from_cache(dynamic_id, lottery_type, item)
        if restored:
            activities.append(apply_p2_to_activity(restored, participation=participations.get(dynamic_id)))
    ordered = sorted(activities, key=lambda entry: entry.dynamic_id)
    enriched_at = int(payload.get("enriched_at") or time.time())
    return EnrichResult(
        enriched_at=enriched_at,
        total_count=len(ordered),
        new_count=0,
        p1_count=sum(1 for entry in ordered if not entry.skipped),
        skipped_count=sum(1 for entry in ordered if entry.skipped),
        cache_hits=len(ordered),
        counts=_build_draw_counts(ordered),
        user_status_counts=_build_user_status_counts(ordered),
        activities=[entry.to_dict() for entry in ordered],
        complete=True,
    )


def fetch_activity_info(
    *,
    workers: int = DEFAULT_WORKERS,
    use_cache: bool = True,
    save_every: int = DEFAULT_SAVE_EVERY,
    force: bool = False,
    backfill_heat: bool = False,
    on_progress: EnrichProgressCallback | None = None,
) -> EnrichResult:
    classified = load_previous_output(CLASSIFIED_OUTPUT_PATH)
    if not classified:
        raise RuntimeError(f"未找到分类结果: {CLASSIFIED_OUTPUT_PATH}")

    classified_items = classified.get("activities") or []
    existing_by_id = _load_existing_activities()
    if backfill_heat and not force:
        stale_reset = _reset_stale_heat_flags(existing_by_id)
        if stale_reset:
            logger.info("重置 %s 条错误热度标记", stale_reset)
    initial_existing_ids = set(existing_by_id.keys())
    participations = load_participations()
    reset_detail_api_state()
    enriched_at = int(time.time())
    newly_enriched: dict[str, EnrichedActivity] = {}
    activities_lock = threading.Lock()
    cache_hits = 0
    processed = 0
    cache_updates: dict[str, dict] = {}

    new_tasks: list[tuple[str, LotteryType]] = []
    backfill_tasks: list[tuple[str, LotteryType, dict]] = []
    task_ids: set[str] = set()
    for item in classified_items:
        dynamic_id = str(item.get("dynamic_id") or "")
        lottery_type = item.get("lottery_type")
        if not dynamic_id or lottery_type not in CLASSIFIABLE_TYPES:
            continue
        if not force and dynamic_id in existing_by_id:
            if backfill_heat and _cache_missing_repost_count(existing_by_id[dynamic_id]):
                backfill_tasks.append((dynamic_id, lottery_type, existing_by_id[dynamic_id]))
                task_ids.add(dynamic_id)
            continue
        new_tasks.append((dynamic_id, lottery_type))
        task_ids.add(dynamic_id)

    if backfill_heat and not force:
        for dynamic_id, cached in existing_by_id.items():
            if dynamic_id in task_ids:
                continue
            lottery_type = cached.get("lottery_type")
            if lottery_type not in CLASSIFIABLE_TYPES:
                continue
            if _cache_missing_repost_count(cached):
                backfill_tasks.append((dynamic_id, lottery_type, cached))
                task_ids.add(dynamic_id)

    if force:
        remove_cache_entries(list(existing_by_id.keys()))
    elif task_ids:
        remove_cache_entries(list(task_ids))

    enrich_total = len(new_tasks)
    backfill_total = len(backfill_tasks)

    def flush_partial(*, complete: bool) -> None:
        with activities_lock:
            merged = _merge_activities(
                classified_items,
                existing_by_id=existing_by_id,
                newly_enriched=newly_enriched,
                participations=participations,
            )
            save_enriched(
                _build_result(
                    merged,
                    enriched_at=enriched_at,
                    cache_hits=cache_hits,
                    new_count=sum(1 for did in newly_enriched if did not in initial_existing_ids),
                    complete=complete,
                )
            )

    if not classified_items:
        return EnrichResult(
            enriched_at=enriched_at,
            total_count=0,
            new_count=0,
            p1_count=0,
            skipped_count=0,
            cache_hits=0,
            counts={"active": 0, "ended": 0, "skipped": 0},
            user_status_counts={"已结束": 0, "已参加": 0, "未参加": 0},
            activities=[],
            complete=True,
        )

    if new_tasks:
        if on_progress:
            on_progress(0, enrich_total, f"正在拉取 {enrich_total} 条新活动详情")
        worker_count = max(1, workers)
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {
                executor.submit(
                    _enrich_one,
                    dynamic_id,
                    lottery_type,
                    use_cache=use_cache,
                    participation=participations.get(dynamic_id),
                ): dynamic_id
                for dynamic_id, lottery_type in new_tasks
            }

            for future in as_completed(futures):
                dynamic_id = futures[future]
                try:
                    activity = future.result()
                except Exception as exc:
                    logger.warning("活动 %s 拉取失败: %s", dynamic_id, exc)
                    continue
                should_flush = False
                with activities_lock:
                    newly_enriched[activity.dynamic_id] = activity
                    if activity.from_cache:
                        cache_hits += 1
                    elif use_cache and not activity.skipped and activity.draw_status == "ended":
                        payload = activity.to_dict()
                        payload.pop("activity_status", None)
                        payload.pop("user_status_source", None)
                        cache_updates[activity.dynamic_id] = payload
                    processed += 1
                    if on_progress and (processed % 5 == 0 or processed == enrich_total):
                        on_progress(processed, enrich_total, f"正在拉取活动详情 ({processed}/{enrich_total})")
                    if processed % 20 == 0 or processed == enrich_total:
                        logger.info("信息拉取进度: %s/%s", processed, enrich_total)
                    should_flush = save_every > 0 and processed % save_every == 0

                if should_flush:
                    if cache_updates:
                        merge_cache(cache_updates)
                        cache_updates.clear()
                    flush_partial(complete=False)

        if cache_updates:
            merge_cache(cache_updates)

    if backfill_tasks:
        backfill_processed = 0
        if on_progress:
            on_progress(0, backfill_total, f"正在补全 {backfill_total} 条活动热度")
        worker_count = max(1, workers)
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {
                executor.submit(
                    _backfill_repost_one,
                    dynamic_id,
                    lottery_type,
                    existing,
                    participation=participations.get(dynamic_id),
                ): dynamic_id
                for dynamic_id, lottery_type, existing in backfill_tasks
            }
            for future in as_completed(futures):
                dynamic_id = futures[future]
                try:
                    activity = future.result()
                except Exception as exc:
                    logger.warning("热度补全失败 %s: %s", dynamic_id, exc)
                    continue
                if activity:
                    with activities_lock:
                        newly_enriched[activity.dynamic_id] = activity
                backfill_processed += 1
                if on_progress and (backfill_processed % 10 == 0 or backfill_processed == backfill_total):
                    on_progress(
                        backfill_processed,
                        backfill_total,
                        f"正在补全活动热度 ({backfill_processed}/{backfill_total})",
                    )
                if save_every > 0 and backfill_processed % save_every == 0:
                    flush_partial(complete=False)

        flush_partial(complete=True)

    if not new_tasks and not backfill_tasks:
        if on_progress:
            on_progress(0, 0, "使用本地活动缓存，无新活动需拉取")

    merged = _merge_activities(
        classified_items,
        existing_by_id=existing_by_id,
        newly_enriched=newly_enriched,
        participations=participations,
    )
    return _build_result(
        merged,
        enriched_at=enriched_at,
        cache_hits=cache_hits,
        new_count=sum(1 for did in newly_enriched if did not in initial_existing_ids),
        complete=True,
    )


def mark_enriched_joined(dynamic_id: str) -> Path | None:
    """参与状态已写入 per-user participations.json，不再回写共用 enriched 文件。"""
    _ = dynamic_id
    return None


def save_enriched(result: EnrichResult) -> Path:
    migrated_times = migrate_stored_lottery_times(result.activities)
    migrated_charging = migrate_stored_charging_lotteries(result.activities)
    if migrated_times:
        logger.info("开奖时间已规范化 %s 条", migrated_times)
    if migrated_charging:
        logger.info("充电抽奖已标记跳过 %s 条", migrated_charging)
    ENRICHED_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = ENRICHED_OUTPUT_PATH.with_suffix(".json.tmp")
    tmp_path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp_path.replace(ENRICHED_OUTPUT_PATH)
    return ENRICHED_OUTPUT_PATH
