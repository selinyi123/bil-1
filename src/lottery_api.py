from __future__ import annotations

import json
import re
import threading

from src.bilibili_client import BilibiliClient
from src.sources.common import opus_link

LOTTERY_NOTICE_URL = "https://api.vc.bilibili.com/lottery_svr/v1/lottery_svr/lottery_notice"
DYNAMIC_DETAIL_URL = "https://api.bilibili.com/x/polymer/web-dynamic/v1/detail"

RESERVE_RESERVED_STATUS = 2

RESERVE_RID_RE = re.compile(r'"rid"\s*:\s*(\d+)')

_detail_api_lock = threading.Lock()
_detail_api_enabled = True


def is_detail_api_enabled() -> bool:
    return _detail_api_enabled


def disable_detail_api() -> None:
    global _detail_api_enabled
    with _detail_api_lock:
        _detail_api_enabled = False


def reset_detail_api_state() -> None:
    global _detail_api_enabled
    with _detail_api_lock:
        _detail_api_enabled = True


def fetch_lottery_notice(
    client: BilibiliClient,
    *,
    business_id: str,
    business_type: int,
    referer: str,
) -> dict | None:
    data = client.request_json(
        LOTTERY_NOTICE_URL,
        {"business_id": business_id, "business_type": business_type},
        referer=referer,
        retries=1,
    )
    if data.get("code") != 0:
        return None
    notice = data.get("data") or {}
    return notice if notice.get("lottery_id") else None


def extract_repost_count_from_detail(item: dict) -> int:
    """从动态详情中提取转发数（热度）。"""
    modules = item.get("modules") or {}
    stat = modules.get("module_stat") or {}
    forward = stat.get("forward") or {}
    count = forward.get("count")
    if count is None:
        return 0
    try:
        return max(0, int(count))
    except (TypeError, ValueError):
        return 0


def fetch_dynamic_detail(client: BilibiliClient, dynamic_id: str) -> dict | None:
    if not is_detail_api_enabled():
        return None
    referer = opus_link(dynamic_id)
    try:
        data = client.get_json(
            DYNAMIC_DETAIL_URL,
            {"id": dynamic_id},
            referer=referer,
            retries=2,
        )
    except Exception:
        return None
    if data.get("code") != 0:
        return None
    return (data.get("data") or {}).get("item") or None


def resolve_reserve_business(
    client: BilibiliClient,
    dynamic_id: str,
) -> tuple[str, int] | None:
    """预约抽奖：解析 reserve.rid 与 business_type=10。"""
    item = fetch_dynamic_detail(client, dynamic_id)
    if item:
        additional = ((item.get("modules") or {}).get("module_dynamic") or {}).get("additional") or {}
        reserve = additional.get("reserve") or {}
        rid = reserve.get("rid")
        if rid:
            return str(rid), 10

    referer = opus_link(dynamic_id)
    try:
        html = client.get_text(referer, referer="https://www.bilibili.com", retries=1)
    except RuntimeError:
        return None
    match = RESERVE_RID_RE.search(html)
    if match:
        return match.group(1), 10
    return None


def fetch_reserve_button_status(client: BilibiliClient, dynamic_id: str) -> bool | None:
    """返回是否已预约。button.status=2 表示已预约。"""
    item = fetch_dynamic_detail(client, dynamic_id)
    if not item:
        return None
    additional = ((item.get("modules") or {}).get("module_dynamic") or {}).get("additional") or {}
    reserve = additional.get("reserve") or {}
    button = reserve.get("button") or {}
    status = button.get("status")
    if status is None:
        return None
    return int(status) == RESERVE_RESERVED_STATUS


def fetch_notice_for_interact(client: BilibiliClient, dynamic_id: str) -> tuple[dict, int, str] | None:
    referer = opus_link(dynamic_id)
    for business_type in (1, 12):
        notice = fetch_lottery_notice(
            client,
            business_id=dynamic_id,
            business_type=business_type,
            referer=referer,
        )
        if notice:
            return notice, business_type, dynamic_id
    return None


def fetch_notice_for_reserve(client: BilibiliClient, dynamic_id: str) -> tuple[dict, int, str] | None:
    resolved = resolve_reserve_business(client, dynamic_id)
    if not resolved:
        return None
    business_id, business_type = resolved
    notice = fetch_lottery_notice(
        client,
        business_id=business_id,
        business_type=business_type,
        referer=opus_link(dynamic_id),
    )
    if not notice:
        return None
    return notice, business_type, business_id
