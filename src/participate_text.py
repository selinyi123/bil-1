from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Literal

from src.bilibili_client import BilibiliClient
from src.lottery_actions import REPLY_MAIN_URL, _api_code
from src.lottery_api import fetch_dynamic_detail
from src.sources.common import opus_link
from src.user_settings import (
    DEFAULT_PARTICIPATE_TEXT,
    MAX_PARTICIPATE_TEXT_LEN,
    get_participate_fallback_text,
    get_participate_text,
    get_participate_text_mode,
)

ParticipateTextSource = Literal["custom", "random_comment", "custom_fallback"]

REPLY_PAGE_SIZE = 20
REPLY_FETCH_PAGES = 3
REPLY_SKIP_HEAD = 5
REPLY_POOL_END_EXCLUSIVE = 65


@dataclass(frozen=True, slots=True)
class ParticipateTextResolution:
    text: str
    source: ParticipateTextSource
    pool_size: int = 0


def _reply_message(reply: object) -> str:
    if not isinstance(reply, dict):
        return ""
    content = reply.get("content") or {}
    if not isinstance(content, dict):
        return ""
    return str(content.get("message") or "")


def _reply_next_cursor(data: dict) -> int | None:
    cursor = data.get("cursor") or {}
    if not isinstance(cursor, dict):
        return None
    if cursor.get("is_end"):
        return None
    next_raw = cursor.get("next")
    if next_raw is None:
        return None
    try:
        return int(next_raw)
    except (TypeError, ValueError):
        return None


def fetch_reply_messages(
    client: BilibiliClient,
    *,
    rid: str,
    comment_type: int,
    referer: str,
    pages: int = REPLY_FETCH_PAGES,
    page_size: int = REPLY_PAGE_SIZE,
) -> list[str]:
    messages: list[str] = []
    next_cursor = 0
    for _ in range(max(1, pages)):
        try:
            payload = client.request_json(
                REPLY_MAIN_URL,
                params={
                    "oid": rid,
                    "type": comment_type,
                    "mode": 3,
                    "next": next_cursor,
                    "ps": page_size,
                },
                referer=referer,
            )
        except RuntimeError:
            break
        if _api_code(payload) != 0:
            break
        data = payload.get("data") or {}
        if not isinstance(data, dict):
            break
        replies = data.get("replies") or []
        if isinstance(replies, list):
            for reply in replies:
                messages.append(_reply_message(reply))
        next_cursor_value = _reply_next_cursor(data)
        if next_cursor_value is None:
            break
        next_cursor = next_cursor_value
    return messages


def build_random_comment_pool(messages: list[str]) -> list[str]:
    return list(messages[REPLY_SKIP_HEAD:REPLY_POOL_END_EXCLUSIVE])


def pick_random_participate_comment(messages: list[str]) -> str | None:
    pool = build_random_comment_pool(messages)
    if not pool:
        return None
    return random.choice(pool)


def _finalize_participate_text(text: str, *, fallback: str = DEFAULT_PARTICIPATE_TEXT) -> str:
    if not text:
        return fallback
    return text[:MAX_PARTICIPATE_TEXT_LEN]


def resolve_comment_rid_and_type(client: BilibiliClient, dynamic_id: str) -> tuple[str, int, str]:
    item = fetch_dynamic_detail(client, dynamic_id)
    if not item:
        raise RuntimeError("无法获取动态详情")
    referer = opus_link(dynamic_id)
    basic = item.get("basic") or {}
    if not isinstance(basic, dict):
        basic = {}
    comment_rid = str(basic.get("comment_id_str") or dynamic_id)
    comment_type = int(basic.get("comment_type") or 17)
    return comment_rid, comment_type, referer


def resolve_participate_text_for_activity(
    client: BilibiliClient,
    *,
    dynamic_id: str,
    explicit_text: str | None = None,
) -> ParticipateTextResolution:
    custom_text = get_participate_text()
    fallback_text = get_participate_fallback_text()
    if explicit_text is not None:
        return ParticipateTextResolution(
            text=_finalize_participate_text(explicit_text),
            source="custom",
        )

    if get_participate_text_mode() != "random_comment":
        return ParticipateTextResolution(text=custom_text, source="custom")

    try:
        comment_rid, comment_type, referer = resolve_comment_rid_and_type(client, dynamic_id)
        messages = fetch_reply_messages(
            client,
            rid=comment_rid,
            comment_type=comment_type,
            referer=referer,
        )
        picked = pick_random_participate_comment(messages)
        pool = build_random_comment_pool(messages)
        if picked is not None:
            return ParticipateTextResolution(
                text=_finalize_participate_text(picked),
                source="random_comment",
                pool_size=len(pool),
            )
    except (RuntimeError, OSError, ValueError, TypeError):
        pass

    return ParticipateTextResolution(
        text=fallback_text,
        source="custom_fallback",
        pool_size=0,
    )
