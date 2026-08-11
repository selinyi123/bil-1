from __future__ import annotations

import random

import pytest

from src.participate_text import (
    REPLY_FETCH_PAGES,
    REPLY_PAGE_SIZE,
    build_random_comment_pool,
    fetch_reply_messages,
    pick_random_participate_comment,
    resolve_participate_text_for_activity,
)
from src.user_settings import (
    set_participate_fallback_text,
    set_participate_text,
    set_participate_text_mode,
)


class _FakeClient:
    def __init__(self, payloads: list[dict]) -> None:
        self._payloads = list(payloads)
        self.calls: list[dict] = []

    def request_json(self, url: str, *, params: dict | None = None, referer: str = "", **kwargs):
        self.calls.append({"url": url, "params": dict(params or {}), "referer": referer})
        if not self._payloads:
            raise RuntimeError("no payload")
        return self._payloads.pop(0)


def _reply(message: str, *, mid: int = 1) -> dict:
    return {"member": {"mid": mid}, "content": {"message": message}}


def _page(replies: list[dict], *, next_cursor: int | None = None, is_end: bool = False) -> dict:
    cursor: dict = {"is_end": is_end}
    if next_cursor is not None:
        cursor["next"] = next_cursor
    return {"code": 0, "data": {"replies": replies, "cursor": cursor}}


def test_build_random_comment_pool_skips_first_five_and_caps_at_sixty() -> None:
    messages = [f"msg-{index}" for index in range(1, 80)]
    pool = build_random_comment_pool(messages)
    assert pool == [f"msg-{index}" for index in range(6, 66)]
    assert len(pool) == 60


def test_pick_random_participate_comment_returns_none_when_not_enough_comments() -> None:
    messages = [f"msg-{index}" for index in range(1, 6)]
    assert pick_random_participate_comment(messages) is None


def test_pick_random_participate_comment_chooses_from_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    messages = [f"msg-{index}" for index in range(1, 30)]
    monkeypatch.setattr(random, "choice", lambda items: items[0])
    assert pick_random_participate_comment(messages) == "msg-6"


def test_fetch_reply_messages_paginates_three_times() -> None:
    client = _FakeClient(
        [
            _page([_reply(f"a-{index}") for index in range(1, 21)], next_cursor=21),
            _page([_reply(f"b-{index}") for index in range(1, 21)], next_cursor=41),
            _page([_reply(f"c-{index}") for index in range(1, 21)], is_end=True),
        ]
    )
    messages = fetch_reply_messages(
        client,
        rid="123",
        comment_type=17,
        referer="https://www.bilibili.com/opus/123",
    )
    assert len(client.calls) == REPLY_FETCH_PAGES
    assert client.calls[0]["params"]["next"] == 0
    assert client.calls[0]["params"]["ps"] == REPLY_PAGE_SIZE
    assert client.calls[1]["params"]["next"] == 21
    assert client.calls[2]["params"]["next"] == 41
    assert len(messages) == 60
    assert messages[0] == "a-1"
    assert messages[-1] == "c-20"


def test_fetch_reply_messages_stops_when_cursor_ends_early() -> None:
    client = _FakeClient(
        [
            _page([_reply("only-one")], is_end=True),
        ]
    )
    messages = fetch_reply_messages(
        client,
        rid="123",
        comment_type=17,
        referer="https://www.bilibili.com/opus/123",
        pages=3,
    )
    assert len(client.calls) == 1
    assert messages == ["only-one"]


def test_resolve_participate_text_custom_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    set_participate_text_mode("custom")
    set_participate_text("@小明 好运连连！")
    resolved = resolve_participate_text_for_activity(
        _FakeClient([]),
        dynamic_id="123",
    )
    assert resolved.source == "custom"
    assert resolved.text == "@小明 好运连连！"


def test_resolve_participate_text_random_mode_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    set_participate_text_mode("random_comment")
    monkeypatch.setattr(
        "src.participate_enhance.load_participate_enhance",
        lambda: {"copy_chat": {"enabled": True, "exclude_author": False, "blockwords": []}},
    )
    set_participate_text("@小明 自定义文案")
    set_participate_fallback_text("好运连连！")

    def fake_resolve(client, dynamic_id: str):
        raise RuntimeError("detail unavailable")

    monkeypatch.setattr(
        "src.participate_text.resolve_comment_rid_and_type",
        fake_resolve,
    )
    resolved = resolve_participate_text_for_activity(
        _FakeClient([]),
        dynamic_id="123",
    )
    assert resolved.source == "custom_fallback"
    assert resolved.text == "好运连连！"


def test_resolve_participate_text_random_mode_uses_default_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_participate_text_mode("random_comment")
    monkeypatch.setattr(
        "src.participate_enhance.load_participate_enhance",
        lambda: {"copy_chat": {"enabled": True, "exclude_author": False, "blockwords": []}},
    )
    set_participate_text("@小明 自定义文案")
    monkeypatch.setattr(
        "src.participate_text.get_participate_fallback_text",
        lambda: "好运连连！",
    )

    def fake_resolve(client, dynamic_id: str):
        raise RuntimeError("detail unavailable")

    monkeypatch.setattr(
        "src.participate_text.resolve_comment_rid_and_type",
        fake_resolve,
    )
    resolved = resolve_participate_text_for_activity(
        _FakeClient([]),
        dynamic_id="123",
    )
    assert resolved.source == "custom_fallback"
    assert resolved.text == "好运连连！"


def test_resolve_participate_text_random_mode_picks_comment(monkeypatch: pytest.MonkeyPatch) -> None:
    set_participate_text_mode("random_comment")
    monkeypatch.setattr(
        "src.participate_enhance.load_participate_enhance",
        lambda: {"copy_chat": {"enabled": True, "exclude_author": False, "blockwords": []}},
    )
    set_participate_fallback_text("好运连连！")

    monkeypatch.setattr(
        "src.participate_text.resolve_comment_rid_and_type",
        lambda client, dynamic_id: ("999", 17, "https://www.bilibili.com/opus/999"),
    )
    messages = [f"msg-{index}" for index in range(1, 21)]
    monkeypatch.setattr(
        "src.participate_text.fetch_reply_messages",
        lambda *args, **kwargs: messages,
    )
    monkeypatch.setattr(random, "choice", lambda items: "msg-8")

    resolved = resolve_participate_text_for_activity(
        _FakeClient([]),
        dynamic_id="999",
    )
    assert resolved.source == "random_comment"
    assert resolved.text == "msg-8"
    assert resolved.pool_size == 15


def test_resolve_participate_text_explicit_override() -> None:
    set_participate_text_mode("random_comment")
    resolved = resolve_participate_text_for_activity(
        _FakeClient([]),
        dynamic_id="123",
        explicit_text="固定文案",
    )
    assert resolved.source == "custom"
    assert resolved.text == "固定文案"


def test_resolve_participate_text_random_mode_ignores_legacy_enabled_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """random_comment 是唯一业务开关；旧 copy_chat.enabled=False 不得静默降级。"""
    set_participate_text_mode("random_comment")
    set_participate_fallback_text("好运连连！")
    monkeypatch.setattr(
        "src.participate_enhance.load_participate_enhance",
        lambda: {"copy_chat": {"enabled": False, "exclude_author": False, "blockwords": []}},
    )
    monkeypatch.setattr(
        "src.participate_text.resolve_comment_rid_and_type",
        lambda client, dynamic_id: ("123", 17, "https://www.bilibili.com/opus/123"),
    )
    messages = [f"msg-{index}" for index in range(1, 21)]
    monkeypatch.setattr(
        "src.participate_text.fetch_reply_messages",
        lambda *args, **kwargs: messages,
    )
    monkeypatch.setattr(random, "choice", lambda items: "msg-9")

    resolved = resolve_participate_text_for_activity(_FakeClient([]), dynamic_id="123")
    assert resolved.source == "random_comment"
    assert resolved.text == "msg-9"

    # 缺省 copy_chat 使用默认过滤配置，也不会关闭 random_comment。
    monkeypatch.setattr("src.participate_enhance.load_participate_enhance", lambda: {})
    monkeypatch.setattr("src.participate_text.fetch_dynamic_detail", lambda *args, **kwargs: {})
    resolved = resolve_participate_text_for_activity(_FakeClient([]), dynamic_id="123")
    assert resolved.source == "random_comment"
    assert resolved.text == "msg-9"
