from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MessageType(str, Enum):
    """消息中心侧栏五类。"""

    DM = "dm"
    REPLY = "reply"
    AT = "at"
    LIKE = "like"
    SYS = "sys"

    @property
    def label(self) -> str:
        return _MESSAGE_TYPE_LABELS[self]

    @classmethod
    def from_key(cls, key: str) -> MessageType:
        normalized = key.strip().lower()
        for item in cls:
            if item.value == normalized:
                return item
        raise ValueError(f"未知消息类型: {key}")


_MESSAGE_TYPE_LABELS: dict[MessageType, str] = {
    MessageType.DM: "我的消息",
    MessageType.REPLY: "回复我的",
    MessageType.AT: "@我的",
    MessageType.LIKE: "收到的赞",
    MessageType.SYS: "系统通知",
}


@dataclass(slots=True)
class MessageEntry:
    """统一消息条目。"""

    msg_type: MessageType
    id: str
    talker_id: int | None = None
    talker_name: str = ""
    timestamp: int = 0
    title: str = ""
    text: str = ""
    unread_count: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DmSession:
    """私信会话摘要。"""

    talker_id: int
    talker_name: str
    unread_count: int
    timestamp: int
    last_text: str
    is_follow: bool
    system_msg_type: int
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def msg_type(self) -> MessageType:
        if self.system_msg_type in _SYSTEM_MSG_TYPES:
            return MessageType.SYS
        return MessageType.DM


_SYSTEM_MSG_TYPES = {1, 5, 7, 8, 9}


def parse_dm_content(content: str | dict[str, Any] | None) -> tuple[str, str]:
    """解析私信 content，返回 (title, text)。"""
    if content is None:
        return "", ""

    payload: dict[str, Any]
    if isinstance(content, dict):
        payload = content
    else:
        text = str(content).strip()
        if not text:
            return "", ""
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return "", text
        if not isinstance(parsed, dict):
            return "", text
        payload = parsed

    title = _pick_text(payload, "title", "subject", "head_title")
    body = _pick_text(
        payload,
        "content",
        "text",
        "desc",
        "description",
        "message",
        "summary",
    )
    if not body:
        jump_text = _pick_text(payload, "jump_text", "jump_text_2", "jump_text_3")
        if jump_text:
            body = jump_text
    return title, body


def _pick_text(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def normalize_feed_item(msg_type: MessageType, item: dict[str, Any]) -> MessageEntry:
    """将 msgfeed 条目归一化为 MessageEntry。"""
    user = item.get("user") or {}
    detail = item.get("item") or {}
    title = str(detail.get("title") or "").strip()
    text = _pick_text(
        detail,
        "source_content",
        "target_reply_content",
        "root_reply_content",
        "message",
        "desc",
    )
    if not text and title:
        text = title
    return MessageEntry(
        msg_type=msg_type,
        id=str(item.get("id") or ""),
        talker_id=int(user.get("mid") or 0) or None,
        talker_name=str(user.get("nickname") or ""),
        timestamp=int(item.get("reply_time") or 0),
        title=title,
        text=text,
        raw=item,
    )


def normalize_dm_message(msg: dict[str, Any], *, talker_id: int | None = None) -> MessageEntry:
    """将私信正文归一化为 MessageEntry。"""
    title, text = parse_dm_content(msg.get("content"))
    sender_uid = int(msg.get("sender_uid") or 0) or None
    system_msg_type = int(msg.get("system_msg_type") or 0)
    msg_type = MessageType.SYS if system_msg_type in _SYSTEM_MSG_TYPES else MessageType.DM
    return MessageEntry(
        msg_type=msg_type,
        id=str(msg.get("msg_key") or msg.get("msg_seqno") or ""),
        talker_id=talker_id or sender_uid,
        talker_name="",
        timestamp=int(msg.get("timestamp") or 0),
        title=title,
        text=text,
        raw=msg,
    )
