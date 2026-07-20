from __future__ import annotations

import time
from typing import Any

from src.db.json_cols import dumps_json, loads_json
from src.db.models import ActivityRow

_PROMOTED_KEYS = (
    "dynamic_id",
    "source_url",
    "lottery_type",
    "business_id",
    "business_type",
    "draw_status",
    "lottery_time",
    "activity_status",
    "draw_tag",
    "status_classified",
    "skipped",
    "platform_participated",
    "reserve_reserved",
    "repost_count",
    "enriched_at",
    "status_code",
    "skip_reason",
    "lottery_detail_url",
    "user_status_source",
)


def _as_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    return bool(value)


def activity_dict_to_row(item: dict[str, Any], *, updated_at: int | None = None) -> ActivityRow:
    dynamic_id = str(item.get("dynamic_id") or "").strip()
    if not dynamic_id:
        raise ValueError("activity missing dynamic_id")
    lottery_time = item.get("lottery_time")
    try:
        lottery_time_i = int(lottery_time) if lottery_time is not None else None
    except (TypeError, ValueError):
        lottery_time_i = None
    enriched_at = item.get("enriched_at")
    try:
        enriched_at_i = int(enriched_at) if enriched_at is not None else None
    except (TypeError, ValueError):
        enriched_at_i = None
    status_code = item.get("status_code")
    try:
        status_code_i = int(status_code) if status_code is not None else None
    except (TypeError, ValueError):
        status_code_i = None
    repost_count = item.get("repost_count")
    try:
        repost_count_i = int(repost_count) if repost_count is not None else None
    except (TypeError, ValueError):
        repost_count_i = None

    return ActivityRow(
        dynamic_id=dynamic_id,
        source_url=str(item["source_url"]) if item.get("source_url") is not None else None,
        lottery_type=str(item["lottery_type"]) if item.get("lottery_type") is not None else None,
        business_id=str(item["business_id"]) if item.get("business_id") is not None else None,
        business_type=str(item["business_type"]) if item.get("business_type") is not None else None,
        draw_status=str(item["draw_status"]) if item.get("draw_status") is not None else None,
        lottery_time=lottery_time_i,
        activity_status=str(item["activity_status"]) if item.get("activity_status") is not None else None,
        draw_tag=str(item["draw_tag"]) if item.get("draw_tag") is not None else None,
        status_classified=bool(item.get("status_classified")),
        skipped=bool(item.get("skipped")),
        platform_participated=_as_bool(item.get("platform_participated")),
        reserve_reserved=_as_bool(item.get("reserve_reserved")),
        repost_count=repost_count_i,
        enriched_at=enriched_at_i,
        status_code=status_code_i,
        skip_reason=str(item["skip_reason"]) if item.get("skip_reason") is not None else None,
        lottery_detail_url=str(item["lottery_detail_url"])
        if item.get("lottery_detail_url") is not None
        else None,
        user_status_source=str(item["user_status_source"])
        if item.get("user_status_source") is not None
        else None,
        payload_json=dumps_json(item),
        updated_at=int(updated_at if updated_at is not None else time.time()),
    )


def row_to_activity_dict(row: ActivityRow) -> dict[str, Any]:
    """以完整 payload_json 为底，再用升格列覆盖可变字段（避免丢嵌套；保留 JSON 原类型）。"""
    base = loads_json(row.payload_json, default={})
    if not isinstance(base, dict):
        base = {}
    item = dict(base)
    item["dynamic_id"] = row.dynamic_id

    def _overlay(key: str, value: Any, *, always: bool = False) -> None:
        if always or value is not None:
            item[key] = value
        elif key not in item:
            item[key] = value

    _overlay("source_url", row.source_url)
    _overlay("lottery_type", row.lottery_type)
    _overlay("business_id", row.business_id)
    # business_type 在 JSON 里常为 int；升格列为 str。优先保留 payload 原类型。
    if "business_type" in base:
        item["business_type"] = base["business_type"]
        if row.business_type is not None and str(base.get("business_type")) != str(row.business_type):
            raw = base["business_type"]
            if isinstance(raw, int):
                try:
                    item["business_type"] = int(row.business_type)
                except (TypeError, ValueError):
                    item["business_type"] = row.business_type
            else:
                item["business_type"] = row.business_type
    else:
        _overlay("business_type", row.business_type)
    _overlay("draw_status", row.draw_status)
    _overlay("lottery_time", row.lottery_time)
    _overlay("activity_status", row.activity_status)
    _overlay("draw_tag", row.draw_tag)
    item["status_classified"] = bool(row.status_classified)
    item["skipped"] = bool(row.skipped)
    _overlay("platform_participated", row.platform_participated)
    _overlay("reserve_reserved", row.reserve_reserved)
    _overlay("repost_count", row.repost_count)
    _overlay("enriched_at", row.enriched_at)
    _overlay("status_code", row.status_code)
    _overlay("skip_reason", row.skip_reason)
    _overlay("lottery_detail_url", row.lottery_detail_url)
    _overlay("user_status_source", row.user_status_source)
    return item
