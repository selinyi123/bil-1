from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.user_data import user_dir

BILIBILI_AT_NOTIFY_URL = "https://message.bilibili.com/#/notify/at"


@dataclass(slots=True)
class AtUnreadAlert:
    increased: bool
    delta: int
    previous: int
    current: int

    def to_dict(self) -> dict[str, int | bool]:
        return {
            "increased": self.increased,
            "delta": self.delta,
            "previous": self.previous,
            "current": self.current,
        }


def message_watch_path(uid: int) -> Path:
    return user_dir(uid) / "message_watch.json"


def _load_watch(uid: int) -> dict[str, Any]:
    path = message_watch_path(uid)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_watch(uid: int, data: dict[str, Any]) -> None:
    path = message_watch_path(uid)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(data)
    payload["updated_at"] = int(time.time())
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def get_last_seen_at_unread(uid: int) -> int | None:
    value = _load_watch(uid).get("last_seen_unread_at")
    if value is None:
        return None
    return int(value)


def evaluate_at_unread_alert(uid: int, current: int) -> AtUnreadAlert:
    """对比本地基线与当前 @ 未读数，必要时下调基线；仅在上升时返回提醒。"""
    current = max(int(current), 0)
    last_seen = get_last_seen_at_unread(uid)

    if last_seen is None:
        _save_watch(uid, {"last_seen_unread_at": current})
        return AtUnreadAlert(increased=False, delta=0, previous=current, current=current)

    if current > last_seen:
        return AtUnreadAlert(
            increased=True,
            delta=current - last_seen,
            previous=last_seen,
            current=current,
        )

    if current < last_seen:
        _save_watch(uid, {"last_seen_unread_at": current})

    return AtUnreadAlert(increased=False, delta=0, previous=last_seen, current=current)


def acknowledge_at_unread(uid: int, current: int) -> int:
    """用户确认已查看后，将基线更新为当前未读数。"""
    baseline = max(int(current), 0)
    _save_watch(uid, {"last_seen_unread_at": baseline})
    return baseline
