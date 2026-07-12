from __future__ import annotations

import json
from pathlib import Path

from src.user_data import get_active_uid, user_dir

DEFAULT_PARTICIPATE_TEXT = "好运连连！"
MAX_PARTICIPATE_TEXT_LEN = 233
GLOBAL_SETTINGS_PATH = Path(__file__).resolve().parents[1] / "config" / "participate_settings.json"


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
