from __future__ import annotations

import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path

from src.bilibili_client import BilibiliClient
from src.classify_cache import get_cached_type, merge_cache
from src.lottery_classifier import (
    CLASSIFIABLE_TYPES,
    LotteryType,
    classify_lottery_type_safe,
    is_detail_api_enabled,
    reset_detail_api_state,
)
from src.merge_links import MERGED_OUTPUT_PATH
from src.sources.common import load_previous_output, normalize_activity_id, opus_link
from src.state_store import DATA_DIR

CLASSIFIED_OUTPUT_PATH = DATA_DIR / "output" / "classified_latest.json"
DEFAULT_WORKERS = 8
DEFAULT_SAVE_EVERY = 10


@dataclass
class ClassifiedActivity:
    dynamic_id: str
    source_url: str
    lottery_type: LotteryType
    from_cache: bool = False
    source_hint: LotteryType | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> ClassifiedActivity | None:
        lottery_type = payload.get("lottery_type")
        dynamic_id = str(payload.get("dynamic_id") or "")
        if not dynamic_id or lottery_type not in CLASSIFIABLE_TYPES:
            return None
        hint = payload.get("source_hint")
        if hint not in CLASSIFIABLE_TYPES:
            hint = None
        return cls(
            dynamic_id=dynamic_id,
            source_url=str(payload.get("source_url") or opus_link(dynamic_id)),
            lottery_type=lottery_type,
            from_cache=bool(payload.get("from_cache")),
            source_hint=hint,
        )


@dataclass
class ClassifyResult:
    classified_at: int
    total_count: int
    new_count: int
    counts: dict[str, int]
    activities: list[dict]
    by_type: dict[str, list[str]]
    cache_hits: int = 0
    detail_api_skipped: bool = False
    complete: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


def _build_counts(activities: list[ClassifiedActivity]) -> dict[str, int]:
    counts = {name: 0 for name in CLASSIFIABLE_TYPES}
    for activity in activities:
        counts[activity.lottery_type] += 1
    return counts


def _build_by_type(activities: list[ClassifiedActivity]) -> dict[str, list[str]]:
    by_type: dict[str, list[str]] = {name: [] for name in CLASSIFIABLE_TYPES}
    for activity in activities:
        by_type[activity.lottery_type].append(activity.source_url)
    return by_type


def _load_existing_classified() -> dict[str, ClassifiedActivity]:
    payload = load_previous_output(CLASSIFIED_OUTPUT_PATH) or {}
    result: dict[str, ClassifiedActivity] = {}
    for item in payload.get("activities") or []:
        if not isinstance(item, dict):
            continue
        restored = ClassifiedActivity.from_dict(item)
        if restored:
            result[restored.dynamic_id] = restored
    return result


def _classify_one(
    dynamic_id: str,
    *,
    hint: LotteryType | None,
    use_cache: bool,
) -> ClassifiedActivity:
    if use_cache:
        cached_type = get_cached_type(dynamic_id)
        if cached_type in CLASSIFIABLE_TYPES:
            return ClassifiedActivity(
                dynamic_id=dynamic_id,
                source_url=opus_link(dynamic_id),
                lottery_type=cached_type,
                from_cache=True,
                source_hint=hint,
            )

    with BilibiliClient() as client:
        lottery_type = classify_lottery_type_safe(client, dynamic_id, hint=hint)

    return ClassifiedActivity(
        dynamic_id=dynamic_id,
        source_url=opus_link(dynamic_id),
        lottery_type=lottery_type,
        from_cache=False,
        source_hint=hint,
    )


def classify_merged_links(
    *,
    workers: int = DEFAULT_WORKERS,
    use_cache: bool = True,
    save_every: int = DEFAULT_SAVE_EVERY,
    force: bool = False,
) -> ClassifyResult:
    merged = load_previous_output(MERGED_OUTPUT_PATH)
    if not merged:
        raise RuntimeError(f"未找到合并结果: {MERGED_OUTPUT_PATH}")

    links = merged.get("activity_links") or []
    link_hints: dict[str, str] = merged.get("link_hints") or {}
    existing_by_id = _load_existing_classified()

    reset_detail_api_state()
    classified_at = int(time.time())
    newly_classified: dict[str, ClassifiedActivity] = {}
    activities_lock = threading.Lock()
    cache_hits = 0
    processed = 0
    cache_updates: dict[str, dict] = {}

    tasks: list[tuple[str, LotteryType | None]] = []
    for url in links:
        dynamic_id = normalize_activity_id(url)
        if not dynamic_id:
            continue
        hint = link_hints.get(dynamic_id)
        if hint not in CLASSIFIABLE_TYPES:
            hint = None
        if not force and dynamic_id in existing_by_id:
            continue
        tasks.append((dynamic_id, hint))

    total = len(tasks)

    def flush_partial(*, complete: bool) -> None:
        with activities_lock:
            ordered = _merge_classified(
                links=links,
                existing_by_id=existing_by_id,
                newly_classified=newly_classified,
            )
            result = ClassifyResult(
                classified_at=classified_at,
                total_count=len(ordered),
                new_count=len(newly_classified),
                counts=_build_counts(ordered),
                activities=[item.to_dict() for item in ordered],
                by_type=_build_by_type(ordered),
                cache_hits=cache_hits,
                detail_api_skipped=not is_detail_api_enabled(),
                complete=complete,
            )
            save_classified(result)

    if not links:
        return ClassifyResult(
            classified_at=classified_at,
            total_count=0,
            new_count=0,
            counts={name: 0 for name in CLASSIFIABLE_TYPES},
            activities=[],
            by_type={name: [] for name in CLASSIFIABLE_TYPES},
            cache_hits=0,
            complete=True,
        )

    if tasks:
        worker_count = max(1, workers)
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {
                executor.submit(
                    _classify_one,
                    dynamic_id,
                    hint=hint,
                    use_cache=use_cache,
                ): dynamic_id
                for dynamic_id, hint in tasks
            }

            for future in as_completed(futures):
                dynamic_id = futures[future]
                try:
                    activity = future.result()
                except Exception as exc:
                    print(f"活动 {dynamic_id} 分类失败: {exc}", file=sys.stderr, flush=True)
                    continue
                should_flush = False
                with activities_lock:
                    newly_classified[activity.dynamic_id] = activity
                    if activity.from_cache:
                        cache_hits += 1
                    elif use_cache:
                        cache_updates[activity.dynamic_id] = {
                            "lottery_type": activity.lottery_type,
                            "classified_at": classified_at,
                        }
                    processed += 1
                    if processed % 20 == 0 or processed == total:
                        print(f"分类进度: {processed}/{total}", file=sys.stderr, flush=True)
                    should_flush = save_every > 0 and processed % save_every == 0

                if should_flush:
                    if cache_updates:
                        merge_cache(cache_updates)
                        cache_updates.clear()
                    flush_partial(complete=False)

        if cache_updates:
            merge_cache(cache_updates)

    ordered = _merge_classified(
        links=links,
        existing_by_id=existing_by_id,
        newly_classified=newly_classified,
    )
    return ClassifyResult(
        classified_at=classified_at,
        total_count=len(ordered),
        new_count=len(newly_classified),
        counts=_build_counts(ordered),
        activities=[item.to_dict() for item in ordered],
        by_type=_build_by_type(ordered),
        cache_hits=cache_hits,
        detail_api_skipped=not is_detail_api_enabled(),
        complete=True,
    )


def _merge_classified(
    *,
    links: list[str],
    existing_by_id: dict[str, ClassifiedActivity],
    newly_classified: dict[str, ClassifiedActivity],
) -> list[ClassifiedActivity]:
    activities: list[ClassifiedActivity] = []
    seen: set[str] = set()
    for url in links:
        dynamic_id = normalize_activity_id(url)
        if not dynamic_id or dynamic_id in seen:
            continue
        seen.add(dynamic_id)
        if dynamic_id in newly_classified:
            activities.append(newly_classified[dynamic_id])
        elif dynamic_id in existing_by_id:
            activities.append(existing_by_id[dynamic_id])

    for dynamic_id, activity in existing_by_id.items():
        if dynamic_id not in seen:
            activities.append(activity)
    return sorted(activities, key=lambda item: item.dynamic_id)


def save_classified(result: ClassifyResult) -> Path:
    CLASSIFIED_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = CLASSIFIED_OUTPUT_PATH.with_suffix(".json.tmp")
    tmp_path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp_path.replace(CLASSIFIED_OUTPUT_PATH)
    return CLASSIFIED_OUTPUT_PATH
