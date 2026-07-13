from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from src.activity_status import DrawStatus, resolve_activity_status
from src.fetch_activity_info import ENRICHED_OUTPUT_PATH
from src.lottery_time import normalize_lottery_time_text
from src.participation_store import ParticipationRecord, load_participations


def _lottery_time_unix(item: dict) -> int | None:
    lottery_time = item.get("lottery_time")
    if lottery_time:
        try:
            return int(lottery_time)
        except (TypeError, ValueError):
            return None

    conditions = item.get("conditions") or {}
    text = str(conditions.get("lottery_time_text") or "").strip()
    if not text:
        return None
    normalized = normalize_lottery_time_text(text)
    if not normalized or not normalized[:4].isdigit():
        return None
    try:
        return int(datetime.strptime(normalized, "%Y-%m-%d %H:%M").timestamp())
    except ValueError:
        return None


def _resolve_row_status(
    item: dict,
    participation: ParticipationRecord | None,
) -> tuple[str, str]:
    lottery_type = item.get("lottery_type")
    if lottery_type not in ("互动抽奖", "转发抽奖", "预约抽奖"):
        return str(item.get("activity_status") or "未参加"), str(item.get("draw_status") or "active")

    draw_status: DrawStatus = "ended" if item.get("draw_status") == "ended" else "active"
    status, _ = resolve_activity_status(
        draw_status=draw_status,
        lottery_type=lottery_type,
        platform_participated=item.get("platform_participated"),
        reserve_reserved=item.get("reserve_reserved"),
        conditions=item.get("conditions") or {},
        participation=participation,
    )
    return status, str(item.get("draw_status") or "active")


def refresh_activity_statuses(*, path: Path | None = None) -> dict[str, Any]:
    target = path or ENRICHED_OUTPUT_PATH
    if not target.exists():
        return {
            "updated": 0,
            "ended_marked": 0,
            "status_counts": {"已结束": 0, "已参加": 0, "未参加": 0},
            "listable_counts": {"已结束": 0, "已参加": 0, "未参加": 0},
            "total": 0,
        }

    payload = json.loads(target.read_text(encoding="utf-8"))
    activities = [item for item in (payload.get("activities") or []) if isinstance(item, dict)]
    participations = load_participations()
    now = int(time.time())

    ended_marked = 0
    updated = 0
    status_counts = {"已结束": 0, "已参加": 0, "未参加": 0}
    listable_counts = {"已结束": 0, "已参加": 0, "未参加": 0}

    for item in activities:
        dynamic_id = str(item.get("dynamic_id") or "")
        participation = participations.get(dynamic_id)
        lottery_time = _lottery_time_unix(item)
        if lottery_time and lottery_time <= now and item.get("draw_status") != "ended":
            item["draw_status"] = "ended"
            ended_marked += 1

        prev_status = str(item.get("activity_status") or "")
        prev_draw = str(item.get("draw_status") or "")
        status, draw_status = _resolve_row_status(item, participation)
        if status != prev_status or draw_status != prev_draw:
            updated += 1
        item["activity_status"] = status

        if status in status_counts:
            status_counts[status] += 1

        can_participate = (
            not item.get("skipped")
            and draw_status == "active"
            and status == "未参加"
        )
        if status == "已参加" or status == "已结束" or (status == "未参加" and can_participate):
            if status in listable_counts:
                listable_counts[status] += 1

    draw_counts = {"active": 0, "ended": 0, "skipped": 0}
    for item in activities:
        if item.get("skipped"):
            draw_counts["skipped"] += 1
        elif item.get("draw_status") == "ended":
            draw_counts["ended"] += 1
        else:
            draw_counts["active"] += 1

    payload["activities"] = activities
    payload["enriched_at"] = int(time.time())
    payload["total_count"] = len(activities)
    payload["counts"] = draw_counts
    payload["user_status_counts"] = status_counts

    tmp_path = target.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(target)

    return {
        "updated": updated,
        "ended_marked": ended_marked,
        "status_counts": status_counts,
        "listable_counts": listable_counts,
        "total": len(activities),
    }
