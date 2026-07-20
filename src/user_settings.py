from __future__ import annotations

import time
from typing import Literal

from src.db.models import UserSettingsRow
from src.db.session import session_scope
from src.db.uids import settings_uid

DEFAULT_PARTICIPATE_TEXT = "好运连连！"
DEFAULT_PARTICIPATE_FALLBACK_TEXT = "好运连连！"
MAX_PARTICIPATE_TEXT_LEN = 233
ParticipateTextMode = Literal["custom", "random_comment"]
DEFAULT_PARTICIPATE_TEXT_MODE: ParticipateTextMode = "custom"
VALID_PARTICIPATE_TEXT_MODES = frozenset({"custom", "random_comment"})


def _load_raw() -> dict:
    uid = settings_uid()
    with session_scope() as session:
        row = session.get(UserSettingsRow, uid)
        if row is None:
            return {}
        return {
            "participate_text": row.participate_text,
            "participate_fallback_text": row.participate_fallback_text,
            "participate_text_mode": row.participate_text_mode,
        }


def _save_raw(data: dict) -> None:
    uid = settings_uid()
    now = int(time.time())
    with session_scope() as session:
        row = session.get(UserSettingsRow, uid)
        if row is None:
            row = UserSettingsRow(uid=uid, updated_at=now)
            session.add(row)
        if "participate_text" in data:
            row.participate_text = data.get("participate_text")
        if "participate_fallback_text" in data:
            row.participate_fallback_text = data.get("participate_fallback_text")
        if "participate_text_mode" in data:
            row.participate_text_mode = data.get("participate_text_mode")
        row.updated_at = now


def normalize_participate_text(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return DEFAULT_PARTICIPATE_TEXT
    return cleaned[:MAX_PARTICIPATE_TEXT_LEN]


def get_participate_text() -> str:
    raw = _load_raw().get("participate_text")
    if isinstance(raw, str) and raw.strip():
        return normalize_participate_text(raw)
    return DEFAULT_PARTICIPATE_TEXT


def set_participate_text(text: str) -> str:
    value = normalize_participate_text(text)
    data = _load_raw()
    data["participate_text"] = value
    _save_raw(data)
    return value


def normalize_participate_fallback_text(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return DEFAULT_PARTICIPATE_FALLBACK_TEXT
    return cleaned[:MAX_PARTICIPATE_TEXT_LEN]


def get_participate_fallback_text() -> str:
    raw = _load_raw().get("participate_fallback_text")
    if isinstance(raw, str) and raw.strip():
        return normalize_participate_fallback_text(raw)
    return DEFAULT_PARTICIPATE_FALLBACK_TEXT


def set_participate_fallback_text(text: str) -> str:
    value = normalize_participate_fallback_text(text)
    data = _load_raw()
    data["participate_fallback_text"] = value
    _save_raw(data)
    return value


def normalize_participate_text_mode(mode: str) -> ParticipateTextMode:
    value = (mode or "").strip().lower()
    if value in VALID_PARTICIPATE_TEXT_MODES:
        return value  # type: ignore[return-value]
    return DEFAULT_PARTICIPATE_TEXT_MODE


def get_participate_text_mode() -> ParticipateTextMode:
    raw = _load_raw().get("participate_text_mode")
    if isinstance(raw, str):
        return normalize_participate_text_mode(raw)
    return DEFAULT_PARTICIPATE_TEXT_MODE


def set_participate_text_mode(mode: str) -> ParticipateTextMode:
    value = normalize_participate_text_mode(mode)
    data = _load_raw()
    data["participate_text_mode"] = value
    _save_raw(data)
    return value
