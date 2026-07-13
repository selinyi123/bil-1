from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.activity_status import resolve_activity_status
from src.fetch_activity_info import ENRICHED_OUTPUT_PATH
from src.lottery_time import format_timestamp, lottery_time_text
from src.merge_links import MERGED_OUTPUT_PATH
from src.participation_store import ParticipationRecord, load_participations
from src.sources.common import load_previous_output
from src.state_store import DATA_DIR
from src.user_data import participation_actions_path

DS_OUTPUTS = {
    "DS-1": DATA_DIR / "output" / "ds1_latest.json",
    "DS-2": DATA_DIR / "output" / "ds2_latest.json",
    "DS-3": DATA_DIR / "output" / "ds3_latest.json",
    "DS-4": DATA_DIR / "output" / "ds4_latest.json",
    "DS-5": DATA_DIR / "output" / "ds5_latest.json",
    "DS-6": DATA_DIR / "output" / "ds6_latest.json",
}
SOURCE_LABELS = {
    "DS-1": "哔哩抽奖小助理",
    "DS-2": "番茄薯条喵",
    "DS-3": "你的抽奖工具人",
    "DS-4": "J君名",
    "DS-5": "互动抽奖娘",
    "DS-6": "糯米是个背包",
}
SOURCE_SPACE_URLS = {
    "DS-1": "https://space.bilibili.com/885439/upload/video",
    "DS-2": "https://space.bilibili.com/3546836235193146/upload/opus",
    "DS-3": "https://space.bilibili.com/100680137/upload/opus",
    "DS-4": "https://space.bilibili.com/126038161/upload/opus",
    "DS-5": "https://space.bilibili.com/3546776042736296/upload/opus",
    "DS-6": "https://space.bilibili.com/492426375/upload/opus",
}


@lru_cache(maxsize=4)
def _cached_json(path_str: str, mtime_ns: int) -> dict:
    _ = mtime_ns
    return load_previous_output(Path(path_str)) or {}


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return _cached_json(str(path), path.stat().st_mtime_ns)


def _activity_title(item: dict) -> str:
    return _prize_summary(item) or str(item.get("dynamic_id") or "未知活动")


def _load_participation_actions() -> dict[str, dict]:
    path = participation_actions_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    latest: dict[str, dict] = {}
    for entry in payload.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        dynamic_id = str(entry.get("dynamic_id") or "")
        if dynamic_id:
            latest[dynamic_id] = entry
    return latest


def _prize_summary(item: dict) -> str:
    prizes = item.get("prizes") or []
    if not prizes:
        return ""
    first = prizes[0] if isinstance(prizes[0], dict) else {}
    description = str(first.get("description") or "").strip()
    count = int(first.get("winner_count") or 0)
    if description and count:
        return f"{description} ×{count}"
    return description or (f"×{count}" if count else "")


def _resolve_activity_status(item: dict, participation: ParticipationRecord | None) -> str:
    lottery_type = item.get("lottery_type")
    if lottery_type not in ("互动抽奖", "转发抽奖", "预约抽奖"):
        return str(item.get("activity_status") or "未参加")
    status, _ = resolve_activity_status(
        draw_status=item.get("draw_status") or "active",
        lottery_type=lottery_type,
        platform_participated=item.get("platform_participated"),
        reserve_reserved=item.get("reserve_reserved"),
        conditions=item.get("conditions") or {},
        participation=participation,
    )
    return status


def _can_participate(item: dict, activity_status: str) -> bool:
    return (
        not item.get("skipped")
        and str(item.get("draw_status") or "") == "active"
        and activity_status != "已参加"
        and activity_status != "已结束"
    )


def _should_list_activity(item: dict, activity_status: str, can_participate: bool) -> bool:
    if activity_status == "已参加":
        return True
    if activity_status == "已结束":
        return True
    if activity_status == "未参加" and can_participate:
        return True
    return False


def invalidate_activity_cache() -> None:
    _cached_json.cache_clear()


def _sort_key(item: dict, *, sort: str, order: str) -> tuple:
    if sort == "heat":
        repost = int(item.get("repost_count") or 0)
        heat_key = -repost if order == "desc" else repost
        return (heat_key, str(item.get("dynamic_id") or ""))
    status_rank = {"未参加": 0, "已参加": 1, "已结束": 2}
    draw_rank = {"active": 0, "ended": 1}
    activity_status = str(item.get("activity_status") or "")
    draw_status = str(item.get("draw_status") or "")
    return (
        status_rank.get(activity_status, 9),
        draw_rank.get(draw_status, 9),
        str(item.get("dynamic_id") or ""),
    )


def _normalize_activity(
    item: dict,
    action_map: dict[str, dict],
    participation: ParticipationRecord | None,
) -> dict[str, Any]:
    dynamic_id = str(item.get("dynamic_id") or "")
    last_action = action_map.get(dynamic_id)
    activity_status = _resolve_activity_status(item, participation)
    can_participate = _can_participate(item, activity_status)
    return {
        "dynamic_id": dynamic_id,
        "source_url": str(item.get("source_url") or ""),
        "activity_title": _activity_title(item),
        "lottery_type": str(item.get("lottery_type") or ""),
        "activity_status": activity_status,
        "draw_status": str(item.get("draw_status") or ""),
        "prize": _prize_summary(item),
        "repost_count": int(item.get("repost_count") or 0),
        "lottery_time": lottery_time_text(item) or "—",
        "skipped": bool(item.get("skipped")),
        "skip_reason": str(item.get("skip_reason") or ""),
        "can_participate": can_participate,
        "last_participation": {
            "status": last_action.get("status") if last_action else None,
            "message": last_action.get("message") if last_action else None,
            "recorded_at": last_action.get("recorded_at") if last_action else None,
            "actions": last_action.get("actions") if last_action else None,
        }
        if last_action
        else None,
    }


def get_summary() -> dict[str, Any]:
    enriched = _load_json(ENRICHED_OUTPUT_PATH)
    merged = _load_json(MERGED_OUTPUT_PATH)
    participations = load_participations()
    status_counts = {"已结束": 0, "已参加": 0, "未参加": 0}
    for item in enriched.get("activities") or []:
        if not isinstance(item, dict):
            continue
        status = _resolve_activity_status(item, participations.get(str(item.get("dynamic_id") or "")))
        status_counts[status] = status_counts.get(status, 0) + 1

    sources: list[dict[str, Any]] = []
    for source_id, path in DS_OUTPUTS.items():
        data = _load_json(path)
        checked_at = data.get("checked_at")
        sources.append(
            {
                "id": source_id,
                "name": SOURCE_LABELS.get(source_id, source_id),
                "updated": bool(data.get("updated")),
                "link_count": len(data.get("activity_links") or []),
                "title": str(data.get("title") or ""),
                "checked_at": checked_at,
                "checked_at_text": format_timestamp(int(checked_at)) if checked_at else "尚未更新",
                "space_url": SOURCE_SPACE_URLS.get(source_id, ""),
                "container_url": str(data.get("container_url") or ""),
            }
        )
    return {
        "enriched_at": enriched.get("enriched_at"),
        "total_count": enriched.get("total_count", 0),
        "new_count": merged.get("new_count", 0),
        "user_status_counts": status_counts,
        "counts": enriched.get("counts") or {},
        "sources": sources,
    }


def list_activities(
    *,
    status: str | None = None,
    lottery_type: str | None = None,
    draw: str | None = None,
    q: str | None = None,
    sort: str | None = None,
    order: str | None = None,
    page: int = 1,
    page_size: int = 30,
) -> dict[str, Any]:
    enriched = _load_json(ENRICHED_OUTPUT_PATH)
    action_map = _load_participation_actions()
    participations = load_participations()
    items = [item for item in (enriched.get("activities") or []) if isinstance(item, dict)]

    normalized: list[dict[str, Any]] = []
    for item in items:
        dynamic_id = str(item.get("dynamic_id") or "")
        participation = participations.get(dynamic_id)
        activity_status = _resolve_activity_status(item, participation)
        can_participate = _can_participate(item, activity_status)
        if not _should_list_activity(item, activity_status, can_participate):
            continue
        row = _normalize_activity(item, action_map, participation)
        normalized.append(row)

    if status:
        normalized = [item for item in normalized if item.get("activity_status") == status]
    if lottery_type:
        normalized = [item for item in normalized if item.get("lottery_type") == lottery_type]
    if draw and not status:
        normalized = [item for item in normalized if item.get("draw_status") == draw]
    if q:
        keyword = q.strip().lower()
        if keyword:

            def _matches(item: dict) -> bool:
                fields = [
                    str(item.get("dynamic_id") or ""),
                    str(item.get("activity_title") or ""),
                    str(item.get("prize") or ""),
                    str(item.get("skip_reason") or ""),
                    str(item.get("lottery_time") or ""),
                ]
                return any(keyword in field.lower() for field in fields if field)

            normalized = [item for item in normalized if _matches(item)]

    sort_mode = (sort or "default").strip().lower()
    sort_order = (order or "desc").strip().lower()
    if sort_order not in ("asc", "desc"):
        sort_order = "desc"
    if sort_mode not in ("heat", "default"):
        sort_mode = "default"
    normalized.sort(key=lambda item: _sort_key(item, sort=sort_mode, order=sort_order))
    total = len(normalized)
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    start = (page - 1) * page_size
    page_items = normalized[start : start + page_size]

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
        "items": page_items,
    }


def lookup_lottery_type(dynamic_id: str) -> str:
    enriched = _load_json(ENRICHED_OUTPUT_PATH)
    for item in enriched.get("activities") or []:
        if str(item.get("dynamic_id") or "") == dynamic_id:
            lottery_type = str(item.get("lottery_type") or "")
            if lottery_type in ("互动抽奖", "转发抽奖", "预约抽奖"):
                return lottery_type
    raise RuntimeError(f"未找到活动 {dynamic_id} 的类型信息")
