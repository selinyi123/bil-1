from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from src.lottery_classifier import is_charging_lottery_activity
from src.lottery_time import format_timestamp, lottery_time_text, resolve_effective_lottery_time_unix
from src.message_watch import BILIBILI_AT_NOTIFY_URL
from src.participation_store import ParticipationRecord
from src.user_data import user_dir

DRAWING_SOON_SECONDS = 3 * 24 * 3600
DrawPhase = Literal["soon", "pending"]


@dataclass(slots=True)
class DrawReminderItem:
    dynamic_id: str
    title: str
    lottery_time_text: str
    lottery_time_unix: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "dynamic_id": self.dynamic_id,
            "title": self.title,
            "lottery_time_text": self.lottery_time_text,
            "lottery_time_unix": self.lottery_time_unix,
        }


def _activity_title(item: dict) -> str:
    prizes = item.get("prizes") or []
    if prizes and isinstance(prizes[0], dict):
        description = str(prizes[0].get("description") or "").strip()
        if description:
            return description
    return str(item.get("dynamic_id") or "未知活动")


def is_user_participated(participation: ParticipationRecord | None) -> bool:
    return participation is not None and participation.user_status == "已参加"


def classify_participated_draw(
    item: dict,
    participation: ParticipationRecord | None,
    *,
    now: int | None = None,
) -> DrawPhase | None:
    """已参加活动的开奖临近阶段（仅「即将开奖」；已过期归活动状态「已结束」，不再单独标记）。"""
    if not is_user_participated(participation):
        return None
    lottery_ts = resolve_effective_lottery_time_unix(item, participation)
    if not lottery_ts:
        return None
    current = int(now if now is not None else time.time())
    if lottery_ts <= current:
        return None
    if current < lottery_ts <= current + DRAWING_SOON_SECONDS:
        return "soon"
    return "pending"


def matches_draw_window_filter(
    item: dict,
    participation: ParticipationRecord | None,
    draw_window: str | None,
    *,
    now: int | None = None,
) -> bool:
    if not draw_window:
        return True
    if draw_window != "soon":
        return True
    if item.get("status_classified"):
        return str(item.get("draw_tag") or "") == "即将开奖"
    return classify_participated_draw(item, participation, now=now) == "soon"


def should_recommend_at_check(
    item: dict,
    participation: ParticipationRecord | None,
    *,
    now: int | None = None,
) -> bool:
    _ = (item, participation, now)
    return False


def compute_draw_reminders(
    activities: list[dict],
    participations: dict[str, ParticipationRecord],
    *,
    now: int | None = None,
) -> dict[str, Any]:
    current = int(now if now is not None else time.time())
    soon: list[DrawReminderItem] = []

    for item in activities:
        if not isinstance(item, dict):
            continue
        dynamic_id = str(item.get("dynamic_id") or "")
        if not dynamic_id:
            continue
        if is_charging_lottery_activity(item):
            continue
        participation = participations.get(dynamic_id)
        phase = classify_participated_draw(item, participation, now=current)
        if phase != "soon":
            continue
        lottery_ts = resolve_effective_lottery_time_unix(item, participation)
        if not lottery_ts:
            continue
        soon.append(
            DrawReminderItem(
                dynamic_id=dynamic_id,
                title=_activity_title(item),
                lottery_time_text=lottery_time_text(item) or format_timestamp(lottery_ts),
                lottery_time_unix=lottery_ts,
            )
        )

    soon.sort(key=lambda item: item.lottery_time_unix)

    return {
        "drawing_soon_count": len(soon),
        "drawing_soon": [item.to_dict() for item in soon[:10]],
        "updated_at": current,
        "at_notify_url": BILIBILI_AT_NOTIFY_URL,
    }


def draw_reminder_path(uid: int) -> Path:
    return user_dir(uid) / "draw_reminder.json"


def load_draw_reminder_snapshot(uid: int) -> dict[str, Any] | None:
    path = draw_reminder_path(uid)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def save_draw_reminder_snapshot(uid: int, snapshot: dict[str, Any]) -> dict[str, Any]:
    path = draw_reminder_path(uid)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(snapshot)
    payload["updated_at"] = int(payload.get("updated_at") or time.time())
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)
    return payload
