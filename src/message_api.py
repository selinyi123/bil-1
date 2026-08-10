from __future__ import annotations

from typing import Any

from src.bilibili_client import BilibiliClient
from src.message_types import (
    DmSession,
    MessageEntry,
    MessageType,
    normalize_dm_message,
    normalize_feed_item,
    parse_dm_content,
)

MESSAGE_REFERER = "https://message.bilibili.com"

SINGLE_UNREAD_URL = "https://api.vc.bilibili.com/session_svr/v1/session_svr/single_unread"
MSGFEED_UNREAD_URL = "https://api.vc.bilibili.com/x/im/web/msgfeed/unread"
GET_SESSIONS_URL = "https://api.vc.bilibili.com/session_svr/v1/session_svr/get_sessions"
FETCH_SESSION_MSGS_URL = "https://api.vc.bilibili.com/svr_sync/v1/svr_sync/fetch_session_msgs"
UPDATE_ACK_URL = "https://api.vc.bilibili.com/session_svr/v1/session_svr/update_ack"

MSGFEED_BASE_URL = "https://api.bilibili.com/x/msgfeed"

_WEB_PARAMS = {"build": 0, "mobi_app": "web"}


def _api_code(payload: dict[str, Any]) -> int:
    code = payload.get("code")
    if code is None:
        return -1
    return int(code)


def _require_ok(payload: dict[str, Any], *, action: str) -> dict[str, Any]:
    code = _api_code(payload)
    if code == -101:
        raise RuntimeError("Cookie 已过期，请重新扫码登录")
    if code != 0:
        message = str(payload.get("message") or payload.get("msg") or "未知错误")
        raise RuntimeError(f"{action}失败: {message}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"{action}失败: 响应缺少 data")
    return data


def get_unread_summary(client: BilibiliClient, *, retries: int = 1) -> dict[str, int]:
    """返回五类未读数。"""
    summary = {msg_type.value: 0 for msg_type in MessageType}

    dm_payload = client.request_json(
        SINGLE_UNREAD_URL,
        params={**_WEB_PARAMS, "unread_type": 0, "show_unfollow_list": 1},
        referer=MESSAGE_REFERER,
        retries=retries,
    )
    if _api_code(dm_payload) == 0:
        dm_data = dm_payload.get("data") or {}
        summary[MessageType.DM.value] = int(dm_data.get("follow_unread") or 0) + int(
            dm_data.get("unfollow_unread") or 0
        )

    feed_payload = client.request_json(
        MSGFEED_UNREAD_URL,
        params=_WEB_PARAMS,
        referer=MESSAGE_REFERER,
        retries=retries,
    )
    if _api_code(feed_payload) == 0:
        feed_data = feed_payload.get("data") or {}
        summary[MessageType.REPLY.value] = int(feed_data.get("reply") or 0)
        summary[MessageType.AT.value] = int(feed_data.get("at") or 0)
        summary[MessageType.LIKE.value] = int(feed_data.get("like") or feed_data.get("recv_like") or 0)
        summary[MessageType.SYS.value] = int(feed_data.get("sys_msg") or 0)

    return summary


def list_dm_sessions(
    client: BilibiliClient,
    *,
    size: int = 20,
    begin_ts: int = 0,
    include_system: bool = False,
) -> list[DmSession]:
    """获取私信会话列表。"""
    params: dict[str, Any] = {
        **_WEB_PARAMS,
        "session_type": 4 if include_system else 1,
        "group_fold": 0,
        "unfollow_fold": 0,
        "sort_rule": 2,
        "size": size,
    }
    if begin_ts:
        params["begin_ts"] = begin_ts

    data = _require_ok(
        client.request_json(GET_SESSIONS_URL, params=params, referer=MESSAGE_REFERER),
        action="获取私信会话",
    )
    sessions: list[DmSession] = []
    for item in data.get("session_list") or []:
        if not isinstance(item, dict):
            continue
        system_msg_type = int(item.get("system_msg_type") or 0)
        if not include_system and system_msg_type in {1, 5, 7, 8, 9}:
            continue
        last_msg = item.get("last_msg") or {}
        title, text = parse_dm_content(last_msg.get("content"))
        talker_id = int(item.get("talker_id") or 0)
        account_info = item.get("account_info") or {}
        talker_name = str(account_info.get("name") or "").strip()
        sessions.append(
            DmSession(
                talker_id=talker_id,
                talker_name=talker_name,
                unread_count=int(item.get("unread_count") or 0),
                timestamp=int(last_msg.get("timestamp") or 0),
                last_text=text or title,
                is_follow=bool(int(item.get("is_follow") or 0)),
                system_msg_type=system_msg_type,
                raw=item,
            )
        )
    return sessions


def fetch_dm_messages(
    client: BilibiliClient,
    talker_id: int,
    *,
    session_type: int = 1,
    size: int = 20,
    end_seqno: int = 0,
) -> list[MessageEntry]:
    """获取与指定对象的私信记录。"""
    params: dict[str, Any] = {
        **_WEB_PARAMS,
        "talker_id": talker_id,
        "session_type": session_type,
        "size": size,
        "sender_device_id": 1,
    }
    if end_seqno:
        params["end_seqno"] = end_seqno

    data = _require_ok(
        client.request_json(FETCH_SESSION_MSGS_URL, params=params, referer=MESSAGE_REFERER),
        action="获取私信记录",
    )
    entries: list[MessageEntry] = []
    for item in data.get("messages") or []:
        if not isinstance(item, dict):
            continue
        entries.append(normalize_dm_message(item, talker_id=talker_id))
    return entries


def list_feed(
    client: BilibiliClient,
    msg_type: MessageType,
    *,
    cursor_id: int = 0,
    cursor_time: int = 0,
    platform: str = "web",
) -> tuple[list[MessageEntry], dict[str, Any]]:
    """获取回复/@/赞通知列表。"""
    if msg_type not in {MessageType.REPLY, MessageType.AT, MessageType.LIKE}:
        raise ValueError(f"list_feed 不支持类型: {msg_type.value}")

    params: dict[str, Any] = {
        **_WEB_PARAMS,
        "platform": platform,
        "web_location": "333.40164",
    }
    if cursor_id:
        params["id"] = cursor_id
    if cursor_time:
        params["reply_time"] = cursor_time

    data = _require_ok(
        client.request_json(
            f"{MSGFEED_BASE_URL}/{msg_type.value}",
            params=params,
            referer=MESSAGE_REFERER,
        ),
        action=f"获取{msg_type.label}",
    )
    items = [normalize_feed_item(msg_type, item) for item in data.get("items") or [] if isinstance(item, dict)]
    cursor = data.get("cursor") or {}
    return items, cursor if isinstance(cursor, dict) else {}


def mark_dm_read(
    client: BilibiliClient,
    talker_id: int,
    *,
    session_type: int = 1,
    seqno: int = 0,
) -> bool:
    """把私信会话标记为已读（中奖深检后避免重复提醒）。

    返回是否成功（网络/业务错误返回 False 不抛）。
    """
    params: dict[str, Any] = {
        **_WEB_PARAMS,
        "talker_id": talker_id,
        "session_type": session_type,
        "ack_seqno": seqno,
    }
    try:
        payload = client.post_form(UPDATE_ACK_URL, params, referer=MESSAGE_REFERER, raise_on_code=False)
        return _api_code(payload) == 0
    except RuntimeError:
        return False


def list_system_notices(
    client: BilibiliClient,
    *,
    size: int = 20,
) -> list[MessageEntry]:
    """获取系统通知列表。"""
    sessions = list_dm_sessions(client, size=size, include_system=True)
    system_sessions = [session for session in sessions if session.msg_type == MessageType.SYS]
    if not system_sessions:
        return []

    entries: list[MessageEntry] = []
    for session in system_sessions:
        messages = fetch_dm_messages(
            client,
            session.talker_id,
            session_type=1,
            size=size,
        )
        for entry in messages:
            entry.talker_name = session.talker_name or entry.talker_name
            entries.append(entry)

    entries.sort(key=lambda item: item.timestamp, reverse=True)
    return entries[:size]
