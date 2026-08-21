from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from src.bilibili_client import BilibiliClient
from src.fetch_activity_info import ENRICHED_OUTPUT_PATH
from src.lottery_api import (
    fetch_dynamic_detail,
    fetch_notice_for_interact,
    fetch_notice_for_reserve,
    fetch_reserve_button_status,
    is_upower_dynamic,
)
from src.lottery_classifier import PARTICIPATABLE_TYPES, is_charging_lottery_activity
from src.lottery_time import lottery_time_unix
from src.participation_store import (
    ParticipationRecord,
    load_participations,
    load_participations_for_uid,
)
from src.sources.common import is_valid_dynamic_id, load_previous_output
from src.status_refresh import persist_activity_record
from src.db.uids import participation_uid


def _load_activity_item(dynamic_id: str) -> dict | None:
    payload = load_previous_output(ENRICHED_OUTPUT_PATH) or {}
    for item in payload.get("activities") or []:
        if isinstance(item, dict) and str(item.get("dynamic_id") or "") == dynamic_id:
            return dict(item)
    return None


def _apply_notice_fields(item: dict, notice: dict, *, observed_uid: str) -> None:
    if "participated" in notice:
        item["platform_participated"] = bool(notice.get("participated"))
        # 平台事实是账号态事实：谁观测到的就记谁，读侧据此决定是否信任。
        item["platform_observed_uid"] = observed_uid
    lottery_time = int(notice.get("lottery_time") or 0)
    if lottery_time:
        item["lottery_time"] = lottery_time
    status = int(notice.get("status") or 0)
    if status != 0 or notice.get("lottery_result"):
        item["draw_status"] = "ended"
    elif lottery_time and lottery_time <= int(time.time()):
        item["draw_status"] = "ended"
    else:
        item["draw_status"] = "active"


def _sync_live_fields(
    client: BilibiliClient,
    item: dict,
    *,
    lottery_type: str,
    observed_uid: str,
) -> None:
    dynamic_id = str(item.get("dynamic_id") or "")
    detail = fetch_dynamic_detail(client, dynamic_id)
    if not detail:
        raise RuntimeError("无法打开活动链接，请稍后重试")
    if is_upower_dynamic(detail):
        raise RuntimeError("充电专属抽奖，不参与")

    if lottery_type == "互动抽奖":
        resolved = fetch_notice_for_interact(client, dynamic_id)
        if not resolved:
            raise RuntimeError("无法获取抽奖信息，活动可能已结束或不可参与")
        notice, _, _ = resolved
        _apply_notice_fields(item, notice, observed_uid=observed_uid)
        return

    if lottery_type == "预约抽奖":
        item["reserve_reserved"] = fetch_reserve_button_status(client, dynamic_id)
        item["platform_observed_uid"] = observed_uid
        try:
            resolved = fetch_notice_for_reserve(client, dynamic_id)
        except RuntimeError:
            resolved = None
        if resolved:
            notice, _, _ = resolved
            _apply_notice_fields(item, notice, observed_uid=observed_uid)
        else:
            lottery_ts = lottery_time_unix(item)
            item["draw_status"] = "ended" if lottery_ts and lottery_ts <= int(time.time()) else "active"
        return

    if lottery_type == "转发抽奖":
        lottery_ts = lottery_time_unix(item)
        item["draw_status"] = "ended" if lottery_ts and lottery_ts <= int(time.time()) else "active"
        return

    raise RuntimeError(f"不支持的抽奖类型: {lottery_type}")


def refresh_activity_status_from_live(
    client: BilibiliClient,
    dynamic_id: str,
    *,
    lottery_type_hint: str | None = None,
    account_uid: str | int | None = None,
) -> dict[str, Any]:
    """打开活动链接同步最新状态，写回本地并返回更新后的记录。"""
    dynamic_id = str(dynamic_id or "").strip()
    if not is_valid_dynamic_id(dynamic_id):
        raise ValueError("活动 ID 无效")

    item = _load_activity_item(dynamic_id)
    if not item:
        raise RuntimeError("未找到活动信息，请先执行一键更新")

    if is_charging_lottery_activity(item):
        raise RuntimeError("充电专属抽奖，不参与")

    lottery_type = str(lottery_type_hint or item.get("lottery_type") or "").strip()
    if lottery_type not in PARTICIPATABLE_TYPES:
        raise RuntimeError("未找到可参与的活动类型，请先执行一键更新")

    item["lottery_type"] = lottery_type
    # 账号绑定任务必须记绑定 UID，而不是"当前 active UID"——后者是环境状态，
    # 任务执行期间可能被切换，正是 account_uid 绑定要消除的依赖。
    observed_uid = str(account_uid) if account_uid is not None else participation_uid()
    _sync_live_fields(client, item, lottery_type=lottery_type, observed_uid=observed_uid)
    if account_uid is None:
        participation = load_participations().get(dynamic_id)
    else:
        participation = load_participations_for_uid(account_uid).get(dynamic_id)
    return persist_activity_record(
        item,
        participation=participation,
        account_uid=account_uid,
    )


def ensure_activity_participatable(
    client: BilibiliClient,
    dynamic_id: str,
    *,
    lottery_type_hint: str | None = None,
    account_uid: str | int | None = None,
) -> dict[str, Any]:
    """参与前检查：同步状态后必须为未参加且未结束。"""
    item = refresh_activity_status_from_live(
        client,
        dynamic_id,
        lottery_type_hint=lottery_type_hint,
        account_uid=account_uid,
    )
    status = str(item.get("activity_status") or "")
    if status != "未参加":
        raise RuntimeError(f"活动当前为「{status}」，无法参与")
    if str(item.get("draw_status") or "") == "ended":
        raise RuntimeError("活动已结束，无法参与")
    return item
