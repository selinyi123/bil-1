from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from src.sources.common import load_previous_output, normalize_activity_id, normalize_activity_url
from src.state_store import DATA_DIR

OUTPUT_DIR = DATA_DIR / "output"
MERGED_OUTPUT_PATH = OUTPUT_DIR / "merged_latest.json"
ENRICHED_OUTPUT_PATH = OUTPUT_DIR / "enriched_latest.json"

SOURCE_OUTPUTS: tuple[tuple[str, Path], ...] = (
    ("DS-1", OUTPUT_DIR / "ds1_latest.json"),
    ("DS-2", OUTPUT_DIR / "ds2_latest.json"),
    ("DS-3", OUTPUT_DIR / "ds3_latest.json"),
    ("DS-4", OUTPUT_DIR / "ds4_latest.json"),
    ("DS-5", OUTPUT_DIR / "ds5_latest.json"),
)


@dataclass
class MergeResult:
    merged_at: int
    total_count: int
    new_count: int
    duplicate_count: int
    sources: dict[str, dict]
    activity_links: list[str]
    link_hints: dict[str, str]
    new_activity_ids: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def _known_activity_ids() -> set[str]:
    enriched = load_previous_output(ENRICHED_OUTPUT_PATH) or {}
    known = {
        str(item.get("dynamic_id"))
        for item in (enriched.get("activities") or [])
        if isinstance(item, dict) and item.get("dynamic_id")
    }
    if known:
        return known

    previous = load_previous_output(MERGED_OUTPUT_PATH) or {}
    return {
        activity_id
        for url in (previous.get("activity_links") or [])
        if (activity_id := normalize_activity_id(url))
    }


def merge_activity_links() -> MergeResult:
    known_ids = _known_activity_ids()
    seen: set[str] = set()
    merged: list[str] = []
    link_hints: dict[str, str] = {}
    new_activity_ids: list[str] = []
    duplicate_count = 0
    sources: dict[str, dict] = {}

    for source_id, path in SOURCE_OUTPUTS:
        data = load_previous_output(path)
        if not data:
            sources[source_id] = {"loaded": False, "count": 0, "path": str(path)}
            continue

        raw_links = data.get("activity_links") or []
        raw_hints = data.get("link_hints") or {}
        source_added = 0
        for raw_url in raw_links:
            normalized = normalize_activity_url(raw_url)
            if not normalized:
                continue

            activity_id = normalize_activity_id(raw_url)
            if not activity_id:
                continue
            if activity_id in seen:
                duplicate_count += 1
                continue

            seen.add(activity_id)
            merged.append(normalized)
            source_added += 1
            if activity_id not in known_ids:
                new_activity_ids.append(activity_id)
            hint = raw_hints.get(activity_id)
            if hint and activity_id not in link_hints:
                link_hints[activity_id] = hint

        sources[source_id] = {
            "loaded": True,
            "count": source_added,
            "raw_count": len(raw_links),
            "hint_count": len(raw_hints),
            "path": str(path),
        }

    return MergeResult(
        merged_at=int(time.time()),
        total_count=len(merged),
        new_count=len(new_activity_ids),
        duplicate_count=duplicate_count,
        sources=sources,
        activity_links=merged,
        link_hints=link_hints,
        new_activity_ids=sorted(new_activity_ids),
    )


def save_merged(result: MergeResult) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = MERGED_OUTPUT_PATH.with_suffix(".json.tmp")
    tmp_path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp_path.replace(MERGED_OUTPUT_PATH)
    return MERGED_OUTPUT_PATH
