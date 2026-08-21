from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Literal

from src.bilibili_auth import require_login
from src.bilibili_client import BilibiliClient
from src.lottery_actions import (
    ACTION_INTERVAL_SEC,
    DEFAULT_PARTICIPATE_TEXT,
    ActionResult,
    execute_full_participation,
    follow_user,
    is_following,
    resolve_sender_uid,
    _api_code,
)
from src.lottery_api import (
    fetch_dynamic_detail,
    fetch_notice_for_interact,
    fetch_notice_for_reserve,
    is_upower_dynamic,
)
from sqlmodel import col, select

from src.db.activity_codec import activity_dict_to_row, row_to_activity_dict
from src.db.json_cols import dumps_json
from src.db.models import ActivityRow, ParticipationActionRow, ParticipationRow
from src.db.session import session_scope
from src.db.uids import participation_uid
from src.participation_log import (
    ParticipationActionRecord,
    ParticipationOutcome,
    participation_succeeded,
    serialize_actions,
    _MAX_ENTRIES_PER_UID,
)
from src.user_data_lock import user_data_thread_lock
from src.participate_text import resolve_participate_text_for_activity
from src.lottery_classifier import PARTICIPATABLE_TYPES
from src.sources.common import is_valid_dynamic_id, opus_link

RESERVE_CLICK_URL = "https://api.bilibili.com/x/dynamic/feed/reserve/click"
RESERVE_RESERVED_STATUS = 2
RESERVE_PARTICIPATE_STEPS = 2


def _require_login_for_client(client: BilibiliClient) -> tuple[str, int]:
    """Use the immutable snapshot for bound jobs; retain legacy test/caller seam."""
    from src.account_context import AccountContext

    if isinstance(getattr(client, "account_context", None), AccountContext):
        return client.require_login()
    return require_login()

@dataclass
class ParticipateResult:
    dynamic_id: str
    lottery_type: str
    status: ParticipationOutcome
    message: str
    action_text: str
    actions: list[ActionResult]
    context_snapshot: dict[str, Any]

    def to_dict(self) -> dict:
        return {
            "dynamic_id": self.dynamic_id,
            "lottery_type": self.lottery_type,
            "status": self.status,
            "message": self.message,
            "action_text": self.action_text,
            "actions": serialize_actions(self.actions),
            "context_snapshot": self.context_snapshot,
        }


def _notice_snapshot(notice: dict | None) -> dict[str, Any]:
    if not notice:
        return {}
    return {
        "lottery_id": notice.get("lottery_id"),
        "sender_uid": notice.get("sender_uid"),
        "need_post": notice.get("need_post"),
        "followed": notice.get("followed"),
        "reposted": notice.get("reposted"),
        "participated": notice.get("participated"),
        "status": notice.get("status"),
        "lottery_time": notice.get("lottery_time"),
    }


def _context_snapshot(context: Any | None, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if context is not None:
        payload = {
            "sender_uid": getattr(context, "sender_uid", None),
            "liked": getattr(context, "liked", None),
            "followed": getattr(context, "followed", None),
            "favorited": getattr(context, "favorited", None),
            "favorite_available": getattr(context, "favorite_available", None),
            "reposted": getattr(context, "reposted", None),
            "commented": getattr(context, "commented", None),
            "comment_rid": getattr(context, "comment_rid", None),
        }
    if extra:
        payload.update(extra)
    return payload


def record_participation_outcome_unlocked(
    record: ParticipationActionRecord,
    *,
    account_uid: str | int | None = None,
    mark_joined: bool,
) -> None:
    """在单个 DB 事务内落盘一次参与结果，保证三表一致。

    (a) participation_actions 动作日志（复用 ParticipationActionRow 构造，含按 uid 裁剪）；
    (b) participations 置为已参加（uid + dynamic_id 复合主键 upsert）；
    (c) activities 活动状态置为已参加（与 mark_enriched_joined 相同的写入结果）。

    调用方须持有 user_data_thread_lock（仅进程内线程互斥）。任一子步骤抛错时整体回滚，
    避免此前多次独立提交造成的部分写入不一致。仅在 mark_joined 时写入
    participations 与 activities（动作日志始终写入）。
    """
    explicit_account = account_uid is not None
    uid = str(account_uid) if explicit_account else participation_uid()
    dynamic_id = str(record.dynamic_id or "").strip()
    now = int(time.time())
    with session_scope() as session:
        # (a) 动作日志
        session.add(
            ParticipationActionRow(
                uid=uid,
                recorded_at=int(record.recorded_at),
                dynamic_id=dynamic_id,
                lottery_type=str(record.lottery_type or ""),
                status=str(record.status or ""),
                message=str(record.message or ""),
                action_text=str(record.action_text or ""),
                actions_json=dumps_json(record.actions or []),
                context_snapshot_json=dumps_json(record.context_snapshot or {}),
            )
        )
        session.flush()
        rows = session.exec(
            select(ParticipationActionRow)
            .where(ParticipationActionRow.uid == uid)
            .order_by(
                col(ParticipationActionRow.recorded_at).desc(),
                col(ParticipationActionRow.id).desc(),
            )
        ).all()
        for stale in rows[_MAX_ENTRIES_PER_UID:]:
            session.delete(stale)

        if not mark_joined or not dynamic_id:
            return

        # (b) participations 已参加
        part = session.get(ParticipationRow, (uid, dynamic_id))
        if part is None:
            session.add(
                ParticipationRow(
                    uid=uid,
                    dynamic_id=dynamic_id,
                    user_status="已参加",
                    updated_at=now,
                    source="participate",
                )
            )
        else:
            part.user_status = "已参加"
            part.updated_at = now
            part.source = "participate"

        # (c) activities 活动状态置为已参加
        # The shared activity row is a legacy compatibility mirror.  An
        # account-bound job must not mark a shared row as joined for every
        # account; its ParticipationRow is the account-specific source of
        # truth.
        if explicit_account:
            return
        activity_row = session.get(ActivityRow, dynamic_id)
        if activity_row is None:
            return
        item = row_to_activity_dict(activity_row)
        item["activity_status"] = "已参加"
        item["draw_tag"] = ""
        item["status_classified"] = True
        if item.get("platform_participated") is not None:
            item["platform_participated"] = True
        updated = activity_dict_to_row(item, updated_at=now)
        for name in ActivityRow.model_fields:
            if name == "dynamic_id":
                continue
            setattr(activity_row, name, getattr(updated, name))


def _persist_result(
    *,
    result: ParticipateResult,
    persist: bool,
    account_uid: str | int | None = None,
) -> None:
    if not persist:
        return
    joined = result.status == "joined" and participation_succeeded(
        result.actions,
        lottery_type=result.lottery_type,
    )
    record = ParticipationActionRecord(
        recorded_at=int(time.time()),
        dynamic_id=result.dynamic_id,
        lottery_type=result.lottery_type,
        status=result.status,
        message=result.message,
        action_text=result.action_text,
        actions=serialize_actions(result.actions),
        context_snapshot=result.context_snapshot,
    )
    with user_data_thread_lock():
        record_participation_outcome_unlocked(
            record,
            account_uid=account_uid,
            mark_joined=joined,
        )


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _is_notice_active(notice: dict | None) -> tuple[bool, str]:
    if not notice:
        return False, "未找到抽奖信息"
    if _safe_int(notice.get("status")) != 0:
        return False, "抽奖已结束或不可参与"
    lottery_time = _safe_int(notice.get("lottery_time"))
    if lottery_time and lottery_time <= int(time.time()):
        return False, "已过开奖时间"
    return True, ""


def _resolve_action_text(
    client: BilibiliClient,
    *,
    dynamic_id: str,
    action_text: str | None,
    account_uid: str | int | None = None,
) -> tuple[str, dict[str, Any]]:
    if action_text is None:
        resolved = resolve_participate_text_for_activity(
            client,
            dynamic_id=dynamic_id,
            account_uid=account_uid,
        )
        return resolved.text, {
            "participate_text_source": resolved.source,
            "participate_text_pool_size": resolved.pool_size,
        }
    text = (action_text or DEFAULT_PARTICIPATE_TEXT).strip() or DEFAULT_PARTICIPATE_TEXT
    return text, {
        "participate_text_source": "custom",
        "participate_text_pool_size": 0,
    }


def participate_five_action_lottery(
    client: BilibiliClient,
    *,
    dynamic_id: str,
    lottery_type: Literal["互动抽奖", "转发抽奖"],
    action_text: str | None = None,
    persist: bool = True,
    on_step: Callable[[int, int, str, str], None] | None = None,
    account_uid: str | int | None = None,
) -> ParticipateResult:
    text, text_meta = _resolve_action_text(
        client,
        dynamic_id=dynamic_id,
        action_text=action_text,
        account_uid=account_uid,
    )
    notice: dict | None = None
    sender_uid: int | None = None

    try:
        detail_item = fetch_dynamic_detail(client, dynamic_id)
        if is_upower_dynamic(detail_item):
            result = ParticipateResult(
                dynamic_id=dynamic_id,
                lottery_type=lottery_type,
                status="skipped",
                message="充电专属抽奖，不参与",
                action_text=text,
                actions=[],
                context_snapshot={},
            )
            _persist_result(result=result, persist=persist, account_uid=account_uid)
            return result
    except RuntimeError:
        pass

    if lottery_type == "互动抽奖":
        resolved = fetch_notice_for_interact(client, dynamic_id)
        if not resolved:
            result = ParticipateResult(
                dynamic_id=dynamic_id,
                lottery_type=lottery_type,
                status="failed",
                message="未找到互动抽奖信息",
                action_text=text,
                actions=[],
                context_snapshot={},
            )
            _persist_result(result=result, persist=persist, account_uid=account_uid)
            return result
        notice, _, _ = resolved
        active, reason = _is_notice_active(notice)
        if not active:
            result = ParticipateResult(
                dynamic_id=dynamic_id,
                lottery_type=lottery_type,
                status="skipped",
                message=reason,
                action_text=text,
                actions=[],
                context_snapshot=_notice_snapshot(notice),
            )
            _persist_result(result=result, persist=persist, account_uid=account_uid)
            return result
        sender_uid = int(notice.get("sender_uid") or 0) or None

    try:
        actions, context = execute_full_participation(
            client,
            dynamic_id=dynamic_id,
            sender_uid=sender_uid,
            action_text=text,
            on_step=on_step,
        )
    except RuntimeError as exc:
        message = str(exc).strip() or "参与失败"
        if "无法获取动态详情" in message:
            message = "无法获取动态详情，请稍后重试"
        result = ParticipateResult(
            dynamic_id=dynamic_id,
            lottery_type=lottery_type,
            status="failed",
            message=message,
            action_text=text,
            actions=[],
            context_snapshot=_notice_snapshot(notice),
        )
        _persist_result(result=result, persist=persist, account_uid=account_uid)
        return result

    if participation_succeeded(actions, lottery_type=lottery_type):
        status: ParticipationOutcome = "joined"
        comment = next((item for item in actions if item.action == "comment"), None)
        if lottery_type == "互动抽奖" and comment and not comment.ok:
            message = "核心操作已完成（评论受限，已视为参与成功）"
        else:
            message = "五项操作均已完成" if lottery_type == "转发抽奖" else "核心操作均已完成"
    else:
        status = "failed"
        failed = [item for item in actions if not item.ok]
        message = failed[-1].detail if failed else "部分操作失败"

    snapshot = _context_snapshot(
        context,
        extra={**_notice_snapshot(notice), **text_meta},
    )
    result = ParticipateResult(
        dynamic_id=dynamic_id,
        lottery_type=lottery_type,
        status=status,
        message=message,
        action_text=text,
        actions=actions,
        context_snapshot=snapshot,
    )
    _persist_result(result=result, persist=persist, account_uid=account_uid)
    return result


def _resolve_reserve_info(client: BilibiliClient, dynamic_id: str) -> dict[str, Any]:
    item = fetch_dynamic_detail(client, dynamic_id)
    if not item:
        raise RuntimeError("无法获取动态详情，预约信息解析失败")
    additional = ((item.get("modules") or {}).get("module_dynamic") or {}).get("additional") or {}
    reserve = additional.get("reserve") or {}
    button = reserve.get("button") or {}
    reserve_id = reserve.get("rid")
    if not reserve_id:
        raise RuntimeError("动态中未找到预约组件 rid")
    sender_uid: int | None
    try:
        sender_uid = resolve_sender_uid(item)
    except RuntimeError:
        sender_uid = None
    return {
        "reserve_id": int(reserve_id),
        "reserve_total": int(reserve.get("reserve_total") or 0),
        "button_status": int(button.get("status") or 0),
        "title": str(reserve.get("title") or ""),
        "sender_uid": sender_uid,
        "referer": opus_link(dynamic_id),
    }


def _reserve_click(
    client: BilibiliClient,
    *,
    dynamic_id: str,
    reserve_id: int,
    reserve_total: int,
    button_status: int,
) -> ActionResult:
    if button_status == RESERVE_RESERVED_STATUS:
        return ActionResult("reserve", True, "已预约，跳过")

    csrf, _ = _require_login_for_client(client)
    referer = opus_link(dynamic_id)
    payload = client.post_json(
        RESERVE_CLICK_URL,
        {
            "reserve_id": reserve_id,
            "cur_btn_status": button_status,
            "dynamic_id_str": dynamic_id,
            "reserve_total": reserve_total,
            "spmid": "333.1369.0.0",
        },
        params={"csrf": csrf},
        referer=referer,
        raise_on_code=False,
    )
    code = _api_code(payload)
    if code == 0:
        data = payload.get("data") or {}
        final_status = int(data.get("final_btn_status") or 0)
        toast = str(data.get("toast") or "")
        if final_status == RESERVE_RESERVED_STATUS:
            return ActionResult("reserve", True, toast or "预约成功")
        if "预约成功" in toast or "已参与" in toast:
            return ActionResult("reserve", True, toast)
        if "取消" in toast:
            return ActionResult("reserve", False, toast or "预约操作被取消")
        return ActionResult(
            "reserve",
            False,
            toast or f"预约结果未确认（status={final_status}）",
        )
    message = str(payload.get("message") or payload.get("msg") or "")
    if "已预约" in message:
        return ActionResult("reserve", True, "已预约")
    return ActionResult("reserve", False, f"code={code} {message}".strip())


def participate_reserve_lottery(
    client: BilibiliClient,
    *,
    dynamic_id: str,
    persist: bool = True,
    on_step: Callable[[int, int, str, str], None] | None = None,
    account_uid: str | int | None = None,
) -> ParticipateResult:
    notice: dict | None = None
    try:
        resolved = fetch_notice_for_reserve(client, dynamic_id)
        if resolved:
            notice, _, _ = resolved
            active, reason = _is_notice_active(notice)
            if not active:
                result = ParticipateResult(
                    dynamic_id=dynamic_id,
                    lottery_type="预约抽奖",
                    status="skipped",
                    message=reason,
                    action_text="",
                    actions=[],
                    context_snapshot=_notice_snapshot(notice),
                )
                _persist_result(result=result, persist=persist, account_uid=account_uid)
                return result
    except RuntimeError:
        notice = None

    try:
        reserve_info = _resolve_reserve_info(client, dynamic_id)
    except (RuntimeError, ValueError) as exc:
        result = ParticipateResult(
            dynamic_id=dynamic_id,
            lottery_type="预约抽奖",
            status="failed",
            message=str(exc),
            action_text="",
            actions=[],
            context_snapshot=_notice_snapshot(notice),
        )
        _persist_result(result=result, persist=persist, account_uid=account_uid)
        return result

    total_steps = RESERVE_PARTICIPATE_STEPS
    sender_uid = _safe_int(reserve_info.get("sender_uid"))
    if not sender_uid:
        sender_uid = _safe_int((notice or {}).get("sender_uid"))
    if not sender_uid:
        result = ParticipateResult(
            dynamic_id=dynamic_id,
            lottery_type="预约抽奖",
            status="failed",
            message="无法解析 UP 主 UID，无法完成关注",
            action_text="",
            actions=[],
            context_snapshot={
                **_notice_snapshot(notice),
                "reserve_id": reserve_info["reserve_id"],
                "reserve_total": reserve_info["reserve_total"],
                "button_status": reserve_info["button_status"],
                "title": reserve_info["title"],
            },
        )
        _persist_result(result=result, persist=persist, account_uid=account_uid)
        return result

    referer = str(reserve_info["referer"])

    if on_step:
        on_step(1, total_steps, f"正在关注（1/{total_steps}）", "follow")
    try:
        csrf, _ = _require_login_for_client(client)
        if is_following(client, uid=sender_uid, referer=referer):
            follow_action = ActionResult("follow", True, f"uid={sender_uid} 已关注，跳过")
        else:
            follow_action = follow_user(client, uid=sender_uid, csrf=csrf, referer=referer)
    except RuntimeError as exc:
        follow_action = ActionResult("follow", False, str(exc).strip() or "关注失败")

    actions: list[ActionResult] = [follow_action]
    snapshot = _context_snapshot(
        None,
        extra={
            **_notice_snapshot(notice),
            "sender_uid": sender_uid,
            "reserve_id": reserve_info["reserve_id"],
            "reserve_total": reserve_info["reserve_total"],
            "button_status": reserve_info["button_status"],
            "title": reserve_info["title"],
        },
    )

    if not follow_action.ok:
        result = ParticipateResult(
            dynamic_id=dynamic_id,
            lottery_type="预约抽奖",
            status="failed",
            message=follow_action.detail,
            action_text="",
            actions=actions,
            context_snapshot=snapshot,
        )
        _persist_result(result=result, persist=persist, account_uid=account_uid)
        return result

    time.sleep(ACTION_INTERVAL_SEC)

    if on_step:
        on_step(2, total_steps, f"正在预约（2/{total_steps}）", "reserve")
    reserve_action = _reserve_click(
        client,
        dynamic_id=dynamic_id,
        reserve_id=reserve_info["reserve_id"],
        reserve_total=reserve_info["reserve_total"],
        button_status=reserve_info["button_status"],
    )
    actions.append(reserve_action)

    if participation_succeeded(actions, lottery_type="预约抽奖"):
        status: ParticipationOutcome = "joined"
        message = "关注与预约均已完成"
    else:
        status = "failed"
        message = reserve_action.detail if not reserve_action.ok else "部分操作失败"

    result = ParticipateResult(
        dynamic_id=dynamic_id,
        lottery_type="预约抽奖",
        status=status,
        message=message,
        action_text="",
        actions=actions,
        context_snapshot=snapshot,
    )
    _persist_result(result=result, persist=persist, account_uid=account_uid)
    return result


def participate_activity(
    client: BilibiliClient,
    *,
    dynamic_id: str,
    lottery_type: str,
    action_text: str | None = None,
    persist: bool = True,
    on_step: Callable[[int, int, str, str], None] | None = None,
    account_uid: str | int | None = None,
) -> ParticipateResult:
    if not is_valid_dynamic_id(dynamic_id):
        raise ValueError("dynamic_id 无效")
    if lottery_type == "充电抽奖":
        result = ParticipateResult(
            dynamic_id=dynamic_id,
            lottery_type=lottery_type,
            status="skipped",
            message="充电专属抽奖，不参与",
            action_text=action_text,
            actions=[],
            context_snapshot={},
        )
        _persist_result(result=result, persist=persist, account_uid=account_uid)
        return result
    if lottery_type not in PARTICIPATABLE_TYPES:
        raise RuntimeError(f"不支持的抽奖类型: {lottery_type}")
    if lottery_type == "互动抽奖":
        return participate_five_action_lottery(
            client,
            dynamic_id=dynamic_id,
            lottery_type="互动抽奖",
            action_text=action_text,
            persist=persist,
            on_step=on_step,
            account_uid=account_uid,
        )
    if lottery_type == "转发抽奖":
        return participate_five_action_lottery(
            client,
            dynamic_id=dynamic_id,
            lottery_type="转发抽奖",
            action_text=action_text,
            persist=persist,
            on_step=on_step,
            account_uid=account_uid,
        )
    if lottery_type == "预约抽奖":
        return participate_reserve_lottery(
            client,
            dynamic_id=dynamic_id,
            persist=persist,
            on_step=on_step,
            account_uid=account_uid,
        )
    raise RuntimeError(f"不支持的抽奖类型: {lottery_type}")
