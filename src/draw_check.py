"""中奖深检（源自 LAS lib/check.js isMe）。

对 @我 / 回复 / 私信三类未读消息做关键词判定（`~` 前缀=黑名单、普通=白名单、
优先级递增，命中即判为"可能中奖"），命中则推送通知；私信判定后标记已读避免重复提醒。

关键词默认值与覆盖：`config/notify.json` 顶层 `"keywords": [...]`。
- 未提供 / null：使用 DEFAULT_KEYWORDS；
- 显式 []：禁用关键词命中，不再偷偷回退默认规则。
"""
from __future__ import annotations

import re
from typing import Any

from src.bilibili_client import BilibiliClient
from src.message_api import (
    fetch_dm_messages,
    list_dm_sessions,
    list_feed,
    mark_dm_read,
)
from src.message_types import MessageEntry, MessageType
from src.notify import send_notify

DEFAULT_KEYWORDS = [
    "~预约成功|预约主题|预约已成功",
    "中奖|恭喜|获得|幸运|抽中|奖品|填写地址|核对信息",
]

_DEFAULT_DM_LIMIT = 30


def judge_keywords(text: str, patterns: list[str] | None = None) -> bool:
    """关键词判定（LAS judge 语义）：`~` 开头为黑名单（命中置 False），
    其余为白名单（命中置 True）；后面的规则优先级更高。

    `patterns is None` 才使用默认规则；显式空列表表示禁用匹配。
    """
    text = str(text or "")
    if not text:
        return False
    result = False
    effective_patterns = DEFAULT_KEYWORDS if patterns is None else patterns
    for raw in effective_patterns:
        raw = str(raw).strip()
        if not raw:
            continue
        is_black = raw.startswith("~")
        pattern = raw[1:] if is_black else raw
        try:
            matched = re.search(pattern, text) is not None
        except re.error:
            matched = pattern in text
        if matched:
            result = not is_black
    return result


def _entry_lines(entries: list[MessageEntry]) -> list[str]:
    lines: list[str] = []
    for entry in entries[:10]:
        line = f"- {entry.talker_name or entry.talker_id}: {entry.text or entry.title}"
        if entry.title and entry.text:
            line = f"- {entry.talker_name or entry.talker_id} [{entry.title}]: {entry.text}"
        if getattr(entry, "raw", None) and isinstance(entry.raw, dict):
            uri = str(entry.raw.get("uri") or "")
            if uri:
                line = f"{line} [{uri}]"
        lines.append(line)
    return lines


def _build_desp(results: dict[str, Any]) -> str:
    parts: list[str] = []
    at = results.get("at") or []
    reply = results.get("reply") or []
    dm = results.get("dm") or []
    if at:
        parts.append("## [@我的]\n" + "\n".join(_entry_lines(at)))
    if reply:
        parts.append("## [回复我的]\n" + "\n".join(_entry_lines(reply)))
    for item in dm:
        talker = str(item.get("talker_name") or item.get("talker_id") or "未知")
        parts.append(f"## [私信·{talker}]\n" + "\n".join(_entry_lines(item.get("entries") or [])))
    return "\n\n".join(parts)


def check_prize_draw(
    client: BilibiliClient,
    *,
    keywords: list[str] | None = None,
    max_reply_entries: int = 20,
    max_dm_sessions: int = 20,
    push: bool = True,
) -> dict[str, Any]:
    """执行中奖深检。

    返回 {at, reply, dm, total, pushed, delivered, acknowledged, send_result}：
    - at/reply：命中的通知条目列表
    - dm：命中的私信会话 [{talker_id, talker_name, entries}]
    - delivered：是否至少一个通知渠道确认送达（不再"调用了 send_notify 就算成功"）
    - acknowledged：私信是否已被标记已读（仅在确认送达后才标记，避免吞掉中奖提醒）
    """
    patterns = keywords if keywords is not None else DEFAULT_KEYWORDS
    results: dict[str, Any] = {"at": [], "reply": [], "dm": []}

    # @ 我的（直接命中关键词判定）
    try:
        entries, _ = list_feed(client, MessageType.AT)
        results["at"] = [
            entry for entry in entries[:max_reply_entries] if judge_keywords(entry.text or entry.title, patterns)
        ]
    except RuntimeError:
        results["at"] = []

    # 回复我的（关键词判定）
    try:
        entries, _ = list_feed(client, MessageType.REPLY)
        results["reply"] = [
            entry for entry in entries[:max_reply_entries] if judge_keywords(entry.text or entry.title, patterns)
        ]
    except RuntimeError:
        results["reply"] = []

    # 私信（未读会话拉取 + 判定；标记已读推迟到确认送达之后，见下方）
    dm_hits: list[dict[str, Any]] = []
    dm_pending_ack: list[tuple[int, int]] = []  # (talker_id, seqno)
    try:
        sessions = list_dm_sessions(client, size=max_dm_sessions)
        for session in sessions:
            if session.unread_count <= 0:
                continue
            try:
                messages = fetch_dm_messages(
                    client,
                    session.talker_id,
                    session_type=1,
                    size=min(session.unread_count, 20),
                )
            except RuntimeError:
                continue
            hits = [
                entry
                for entry in messages
                if judge_keywords(entry.text or entry.title, patterns)
            ]
            if hits:
                dm_hits.append(
                    {
                        "talker_id": session.talker_id,
                        "talker_name": session.talker_name,
                        "entries": hits,
                    }
                )
                seqno = int(session.raw.get("last_msg_seqno") or 0) if session.raw else 0
                dm_pending_ack.append((session.talker_id, seqno))
    except RuntimeError:
        pass
    results["dm"] = dm_hits

    total = len(results["at"]) + len(results["reply"]) + sum(len(item.get("entries") or []) for item in dm_hits)
    results["total"] = total

    delivered = False
    acknowledged = False
    send_result: dict[str, Any] = {"sent": [], "skipped": []}
    if push and total > 0:
        desp = _build_desp(results)
        send_result = send_notify("Binggo：账号可能中奖了", desp)
        # 送达确认：至少一个渠道被 provider 确认成功才视为已送达。
        # 未送达（全部渠道失败 / push=False）时**不标记私信已读**，
        # 保留未读状态供下次扫描继续提醒（修复：此前送达前就 mark read 会吞掉中奖提醒）。
        delivered = bool(send_result.get("sent"))
        if delivered and dm_pending_ack:
            ack_ok = True
            for talker_id, seqno in dm_pending_ack:
                # mark_dm_read 失败返回 False（不抛异常），必须检查返回值
                if not mark_dm_read(client, talker_id, seqno=seqno):
                    ack_ok = False
            acknowledged = ack_ok
    results["pushed"] = delivered
    results["delivered"] = delivered
    results["acknowledged"] = acknowledged
    results["send_result"] = send_result
    return results
