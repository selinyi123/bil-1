from __future__ import annotations

import re
import threading
import time
from typing import Literal

from src.bilibili_client import BilibiliClient
from src.sources.common import opus_link

LotteryType = Literal["转发抽奖", "预约抽奖", "互动抽奖"]

LOTTERY_NOTICE_URL = "https://api.vc.bilibili.com/lottery_svr/v1/lottery_svr/lottery_notice"
DYNAMIC_DETAIL_URL = "https://api.bilibili.com/x/polymer/web-dynamic/v1/detail"

RESERVE_MARKER_RE = re.compile(r"reserve_total|ADDITIONAL_TYPE_RESERVE")

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


def _has_lottery_notice(client: BilibiliClient, dynamic_id: str, *, business_type: int) -> bool:
    referer = opus_link(dynamic_id)
    data = client.request_json(
        LOTTERY_NOTICE_URL,
        {"business_id": dynamic_id, "business_type": business_type},
        referer=referer,
        retries=1,
    )
    if data.get("code") != 0:
        return False
    notice = data.get("data") or {}
    return bool(notice.get("lottery_id"))


def _get_dynamic_additional(client: BilibiliClient, dynamic_id: str) -> dict | None:
    if not is_detail_api_enabled():
        return None

    referer = opus_link(dynamic_id)
    try:
        data = client.get_json(
            DYNAMIC_DETAIL_URL,
            {"id": dynamic_id},
            referer=referer,
            retries=1,
        )
    except Exception:
        disable_detail_api()
        return None
    item = (data.get("data") or {}).get("item") or {}
    module_dynamic = (item.get("modules") or {}).get("module_dynamic") or {}
    return module_dynamic.get("additional") or {}


def _has_reserve_from_page(client: BilibiliClient, dynamic_id: str) -> bool:
    try:
        html = client.get_text(opus_link(dynamic_id), referer="https://www.bilibili.com", retries=1)
    except RuntimeError:
        return False
    return bool(RESERVE_MARKER_RE.search(html))


def classify_lottery_type(
    client: BilibiliClient,
    dynamic_id: str,
    *,
    hint: LotteryType | None = None,
) -> LotteryType:
    """根据 B 站 API 特征判定抽奖类型（短路 + 分区提示加速）。"""
    if _has_lottery_notice(client, dynamic_id, business_type=1):
        return "互动抽奖"
    if _has_lottery_notice(client, dynamic_id, business_type=12):
        return "互动抽奖"

    if hint == "转发抽奖":
        return "转发抽奖"

    if hint == "预约抽奖":
        if _has_reserve_from_page(client, dynamic_id):
            return "预约抽奖"
        return "预约抽奖"

    additional = _get_dynamic_additional(client, dynamic_id)
    if additional:
        if additional.get("upower_lottery") or additional.get("type") == "ADDITIONAL_TYPE_UPOWER_LOTTERY":
            return "互动抽奖"
        if additional.get("reserve"):
            return "预约抽奖"

    if hint == "互动抽奖":
        return "互动抽奖"

    if _has_reserve_from_page(client, dynamic_id):
        return "预约抽奖"

    if hint in ("转发抽奖", "预约抽奖", "互动抽奖"):
        return hint

    return "转发抽奖"


def classify_lottery_type_safe(
    client: BilibiliClient,
    dynamic_id: str,
    *,
    hint: LotteryType | None = None,
    retries: int = 1,
) -> LotteryType:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return classify_lottery_type(client, dynamic_id, hint=hint)
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(1.0 * (attempt + 1))
    raise RuntimeError(f"分类失败 dynamic_id={dynamic_id}: {last_error}") from last_error
