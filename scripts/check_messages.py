"""消息中心探针 — 查看未读数、私信会话与五类通知。"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.bilibili_client import BilibiliClient
from src.message_api import (
    fetch_dm_messages,
    get_unread_summary,
    list_dm_sessions,
    list_feed,
    list_system_notices,
)
from src.message_types import MessageType


def _format_time(timestamp: int) -> str:
    if not timestamp:
        return "-"
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def _print_unread_summary() -> int:
    with BilibiliClient() as client:
        summary = get_unread_summary(client)

    print("消息中心未读数：")
    for msg_type in MessageType:
        count = summary.get(msg_type.value, 0)
        print(f"  {msg_type.label}: {count}")
    return 0


def _print_dm_sessions(talker: int | None, size: int) -> int:
    with BilibiliClient() as client:
        if talker is not None:
            messages = fetch_dm_messages(client, talker, size=size)
            if not messages:
                print(f"未找到与 {talker} 的私信记录")
                return 0
            print(f"与 {talker} 的私信记录（{len(messages)} 条）：")
            for entry in messages:
                title = f"[{entry.title}] " if entry.title else ""
                print(f"  [{_format_time(entry.timestamp)}] {title}{entry.text}")
            return 0

        sessions = list_dm_sessions(client, size=size)
        if not sessions:
            print("暂无私信会话")
            return 0

        print(f"私信会话（{len(sessions)} 个）：")
        for session in sessions:
            unread = f" 未读{session.unread_count}" if session.unread_count else ""
            name = session.talker_name or f"UID {session.talker_id}"
            preview = session.last_text.replace("\n", " ").strip()
            if len(preview) > 80:
                preview = preview[:77] + "..."
            print(
                f"  [{_format_time(session.timestamp)}] {name} (mid={session.talker_id})"
                f"{unread}: {preview}"
            )
    return 0


def _print_feed(msg_type: MessageType, size: int) -> int:
    with BilibiliClient() as client:
        if msg_type == MessageType.SYS:
            entries = list_system_notices(client, size=size)
        elif msg_type == MessageType.DM:
            return _print_dm_sessions(None, size)
        else:
            entries, _cursor = list_feed(client, msg_type)

    if not entries:
        print(f"暂无{msg_type.label}")
        return 0

    print(f"{msg_type.label}（{len(entries[:size])} 条）：")
    for entry in entries[:size]:
        name = entry.talker_name or (f"UID {entry.talker_id}" if entry.talker_id else "系统")
        title = f"[{entry.title}] " if entry.title else ""
        text = entry.text.replace("\n", " ").strip()
        if len(text) > 100:
            text = text[:97] + "..."
        print(f"  [{_format_time(entry.timestamp)}] {name}: {title}{text}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="查看 B 站消息中心未读数与消息列表")
    parser.add_argument(
        "--type",
        choices=[item.value for item in MessageType],
        help="消息类型；不指定时仅打印未读数",
    )
    parser.add_argument(
        "--talker",
        type=int,
        help="私信对象 mid，仅 --type dm 时有效",
    )
    parser.add_argument(
        "--size",
        type=int,
        default=20,
        help="列表条数（默认 20）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if not args.type:
            return _print_unread_summary()
        msg_type = MessageType.from_key(args.type)
        if msg_type == MessageType.DM:
            return _print_dm_sessions(args.talker, args.size)
        return _print_feed(msg_type, args.size)
    except RuntimeError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
