from __future__ import annotations

from typing import Any

import pytest

from src.message_api import get_unread_summary, list_dm_sessions, list_feed
from src.message_types import (
    DmSession,
    MessageType,
    normalize_dm_message,
    normalize_feed_item,
    parse_dm_content,
)


def test_message_type_labels() -> None:
    assert MessageType.DM.label == "我的消息"
    assert MessageType.REPLY.label == "回复我的"
    assert MessageType.AT.label == "@我的"
    assert MessageType.LIKE.label == "收到的赞"
    assert MessageType.SYS.label == "系统通知"


def test_message_type_from_key() -> None:
    assert MessageType.from_key("dm") == MessageType.DM
    assert MessageType.from_key("REPLY") == MessageType.REPLY


def test_parse_dm_content_plain_text() -> None:
    title, text = parse_dm_content('{"content":"恭喜中奖"}')
    assert title == ""
    assert text == "恭喜中奖"


def test_parse_dm_content_notification_body() -> None:
    payload = (
        '{"title":"流量奖励到账通知","text":"恭喜您已获得2000流量曝光奖励，快来投稿使用吧。"}'
    )
    title, text = parse_dm_content(payload)
    assert title == "流量奖励到账通知"
    assert "2000流量曝光奖励" in text


def test_parse_dm_content_non_json() -> None:
    title, text = parse_dm_content("hello")
    assert title == ""
    assert text == "hello"


def test_normalize_feed_item_reply() -> None:
    item = {
        "id": 123,
        "reply_time": 1749474709,
        "user": {"mid": 42, "nickname": "测试用户"},
        "item": {
            "title": "动态标题",
            "source_content": "这是回复内容",
        },
    }
    entry = normalize_feed_item(MessageType.REPLY, item)
    assert entry.msg_type == MessageType.REPLY
    assert entry.id == "123"
    assert entry.talker_id == 42
    assert entry.talker_name == "测试用户"
    assert entry.title == "动态标题"
    assert entry.text == "这是回复内容"


def test_normalize_dm_message() -> None:
    msg = {
        "sender_uid": 999,
        "content": '{"content":"私信正文"}',
        "timestamp": 1654154093,
        "msg_key": 7104537732714964358,
        "system_msg_type": 0,
    }
    entry = normalize_dm_message(msg, talker_id=999)
    assert entry.msg_type == MessageType.DM
    assert entry.text == "私信正文"
    assert entry.talker_id == 999


def test_dm_session_type_detection() -> None:
    dm_session = DmSession(
        talker_id=1,
        talker_name="用户",
        unread_count=0,
        timestamp=0,
        last_text="",
        is_follow=True,
        system_msg_type=0,
    )
    sys_session = DmSession(
        talker_id=2,
        talker_name="系统通知",
        unread_count=1,
        timestamp=0,
        last_text="",
        is_follow=False,
        system_msg_type=5,
    )
    assert dm_session.msg_type == MessageType.DM
    assert sys_session.msg_type == MessageType.SYS


class _FakeClient:
    def __init__(self, responses: dict[str, dict[str, Any]]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    def request_json(
        self,
        url: str,
        params: dict | None = None,
        *,
        referer: str | None = None,
        retries: int = 3,
    ) -> dict[str, Any]:
        self.calls.append((url, params))
        for key, payload in self._responses.items():
            if key in url:
                return payload
        raise AssertionError(f"unexpected url: {url}")


def test_get_unread_summary_maps_five_types() -> None:
    client = _FakeClient(
        {
            "single_unread": {
                "code": 0,
                "data": {"follow_unread": 6, "unfollow_unread": 1},
            },
            "msgfeed/unread": {
                "code": 0,
                "data": {
                    "reply": 4,
                    "at": 3,
                    "like": 10,
                    "sys_msg": 2,
                },
            },
        }
    )
    summary = get_unread_summary(client)
    assert summary == {
        "dm": 7,
        "reply": 4,
        "at": 3,
        "like": 10,
        "sys": 2,
    }


def test_list_dm_sessions_filters_system_sessions() -> None:
    client = _FakeClient(
        {
            "get_sessions": {
                "code": 0,
                "data": {
                    "session_list": [
                        {
                            "talker_id": 123,
                            "unread_count": 2,
                            "is_follow": 1,
                            "system_msg_type": 0,
                            "last_msg": {
                                "timestamp": 1712305278,
                                "content": '{"content":"你好"}',
                            },
                        },
                        {
                            "talker_id": 844424930131966,
                            "unread_count": 1,
                            "is_follow": 1,
                            "system_msg_type": 5,
                            "account_info": {"name": "系统通知"},
                            "last_msg": {
                                "timestamp": 1712305279,
                                "content": '{"title":"系统通知","text":"平台消息"}',
                            },
                        },
                    ]
                },
            }
        }
    )
    sessions = list_dm_sessions(client, size=10)
    assert len(sessions) == 1
    assert sessions[0].talker_id == 123
    assert sessions[0].last_text == "你好"


def test_list_feed_reply() -> None:
    client = _FakeClient(
        {
            "/x/msgfeed/reply": {
                "code": 0,
                "data": {
                    "cursor": {"is_end": True, "id": 1, "time": 1},
                    "items": [
                        {
                            "id": 1,
                            "reply_time": 1,
                            "user": {"mid": 7, "nickname": "回复者"},
                            "item": {"title": "标题", "source_content": "回复"},
                        }
                    ],
                },
            }
        }
    )
    entries, cursor = list_feed(client, MessageType.REPLY)
    assert len(entries) == 1
    assert entries[0].msg_type == MessageType.REPLY
    assert entries[0].text == "回复"
    assert cursor["is_end"] is True
