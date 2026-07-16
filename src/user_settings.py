from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from src.user_data import get_active_uid, user_dir

DEFAULT_PARTICIPATE_TEXT = "好运连连！"
DEFAULT_PARTICIPATE_FALLBACK_TEXT = "好运连连！"
MAX_PARTICIPATE_TEXT_LEN = 233
ParticipateTextMode = Literal["custom", "random_comment"]
DEFAULT_PARTICIPATE_TEXT_MODE: ParticipateTextMode = "custom"
VALID_PARTICIPATE_TEXT_MODES = frozenset({"custom", "random_comment"})
from src.app_paths import GLOBAL_SETTINGS_PATH


def _settings_path() -> Path:
    uid = get_active_uid()
    if uid:
        return user_dir(uid) / "settings.json"
    return GLOBAL_SETTINGS_PATH


def _load_raw() -> dict:
    path = _settings_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_raw(data: dict) -> None:
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


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
