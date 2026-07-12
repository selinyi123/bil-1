from __future__ import annotations

import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path

from src.bilibili_client import BilibiliClient
from src.classify_links import CLASSIFIED_OUTPUT_PATH
from src.enrich_cache import get_cached_entry, merge_cache
from src.lottery_api import reset_detail_api_state
from src.lottery_enricher import (
    EnrichedActivity,
    activity_from_cache,
    apply_p2_to_activity,
    enrich_activity,
    enrich_forward_activity,
)
from src.lottery_classifier import LotteryType
from src.participation_store import ParticipationRecord, load_participations
from src.sources.common import load_previous_output
from src.state_store import DATA_DIR

ENRICHED_OUTPUT_PATH = DATA_DIR / "output" / "enriched_latest.json"
DEFAULT_WORKERS = 8
DEFAULT_SAVE_EVERY = 10


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


def _should_use_cache(cached: dict, *, force: bool) -> bool:
    if force:
        return False
    if cached.get("skipped"):
        return False
    return cached.get("draw_status") == "ended"


def _enrich_one(
    dynamic_id: str,
    lottery_type: LotteryType,
    *,
    use_cache: bool,
    participation: ParticipationRecord | None,
) -> EnrichedActivity:
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
        if not dynamic_id or lottery_type not in ("转发抽奖", "预约抽奖", "互动抽奖"):
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


def fetch_activity_info(
    *,
    workers: int = DEFAULT_WORKERS,
    use_cache: bool = True,
    save_every: int = DEFAULT_SAVE_EVERY,
    force: bool = False,
) -> EnrichResult:
    classified = load_previous_output(CLASSIFIED_OUTPUT_PATH)
    if not classified:
        raise RuntimeError(f"未找到分类结果: {CLASSIFIED_OUTPUT_PATH}")

    classified_items = classified.get("activities") or []
    existing_by_id = _load_existing_activities()
    participations = load_participations()
    reset_detail_api_state()
    enriched_at = int(time.time())
    newly_enriched: dict[str, EnrichedActivity] = {}
    activities_lock = threading.Lock()
    cache_hits = 0
    processed = 0
    cache_updates: dict[str, dict] = {}

    tasks: list[tuple[str, LotteryType]] = []
    for item in classified_items:
        dynamic_id = str(item.get("dynamic_id") or "")
        lottery_type = item.get("lottery_type")
        if not dynamic_id or lottery_type not in ("转发抽奖", "预约抽奖", "互动抽奖"):
            continue
        if not force and dynamic_id in existing_by_id:
            continue
        tasks.append((dynamic_id, lottery_type))

    total = len(tasks)

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
                    new_count=len(newly_enriched),
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

    if tasks:
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
                for dynamic_id, lottery_type in tasks
            }

            for future in as_completed(futures):
                activity = future.result()
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
                    if processed % 20 == 0 or processed == total:
                        print(f"信息拉取进度: {processed}/{total}", file=sys.stderr, flush=True)
                    should_flush = save_every > 0 and processed % save_every == 0

                if should_flush:
                    if cache_updates:
                        merge_cache(cache_updates)
                        cache_updates.clear()
                    flush_partial(complete=False)

        if cache_updates:
            merge_cache(cache_updates)

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
        new_count=len(newly_enriched),
        complete=True,
    )


def mark_enriched_joined(dynamic_id: str) -> Path | None:
    """参与状态已写入 per-user participations.json，不再回写共用 enriched 文件。"""
    _ = dynamic_id
    return None


def save_enriched(result: EnrichResult) -> Path:
    ENRICHED_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ENRICHED_OUTPUT_PATH.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return ENRICHED_OUTPUT_PATH
