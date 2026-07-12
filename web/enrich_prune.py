from __future__ import annotations

import time
from typing import Any

from src.fetch_activity_info import EnrichResult


def prune_ended_activities(result: EnrichResult) -> tuple[EnrichResult, int]:
    before = len(result.activities)
    kept = [
        item
        for item in result.activities
        if item.get("draw_status") == "active" and item.get("activity_status") != "已结束"
    ]
    removed = before - len(kept)

    draw_counts = {"active": 0, "ended": 0, "skipped": 0}
    user_status_counts = {"已结束": 0, "已参加": 0, "未参加": 0}
    for item in kept:
        if item.get("skipped"):
            draw_counts["skipped"] += 1
        elif item.get("draw_status") == "ended":
            draw_counts["ended"] += 1
        else:
            draw_counts["active"] += 1
        status = str(item.get("activity_status") or "")
        if status in user_status_counts:
            user_status_counts[status] += 1

    pruned = EnrichResult(
        enriched_at=int(time.time()),
        total_count=len(kept),
        new_count=result.new_count,
        p1_count=sum(1 for item in kept if not item.get("skipped")),
        skipped_count=sum(1 for item in kept if item.get("skipped")),
        cache_hits=result.cache_hits,
        counts=draw_counts,
        user_status_counts=user_status_counts,
        activities=sorted(kept, key=lambda entry: str(entry.get("dynamic_id") or "")),
        complete=True,
    )
    return pruned, removed
