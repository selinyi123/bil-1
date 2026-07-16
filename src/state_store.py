from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from src.app_paths import DATA_DIR, ensure_user_dirs

STATE_PATH = DATA_DIR / "state.json"
_state_lock = threading.Lock()


def _read_state_unlocked() -> dict:
    if not STATE_PATH.exists():
        return {"sources": {}}
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"sources": {}}
    state.setdefault("sources", {})
    return state


def _write_state_unlocked(state: dict) -> None:
    ensure_user_dirs()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = STATE_PATH.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(STATE_PATH)


def load_state() -> dict:
    with _state_lock:
        return _read_state_unlocked()


def save_state(state: dict) -> None:
    with _state_lock:
        _write_state_unlocked(state)


def get_last_container(source_id: str) -> str | None:
    return load_state().get("sources", {}).get(source_id, {}).get("container_url")


def get_last_cv_id(source_id: str) -> str | None:
    return load_state().get("sources", {}).get(source_id, {}).get("cv_id")


def set_last_container(
    source_id: str,
    container_url: str,
    *,
    container_id: str | None = None,
    title: str | None = None,
    cv_id: str | None = None,
) -> None:
    with _state_lock:
        state = _read_state_unlocked()
        entry = {
            "container_url": container_url,
            "container_id": container_id,
            "title": title,
            "checked_at": int(time.time()),
        }
        if cv_id is not None:
            entry["cv_id"] = cv_id
        state.setdefault("sources", {})[source_id] = entry
        _write_state_unlocked(state)


def get_watch_last_synced_at() -> int | None:
    value = load_state().get("watch", {}).get("last_synced_at")
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def set_watch_last_synced_at(timestamp: int) -> None:
    with _state_lock:
        state = _read_state_unlocked()
        watch = dict(state.get("watch") or {})
        watch["last_synced_at"] = int(timestamp)
        state["watch"] = watch
        _write_state_unlocked(state)


def set_last_pipeline_persisted(*, action: str, persisted_count: int, synced_at: int | None = None) -> None:
    """记录最近一次一键更新/监控更新流水线的新入库数。"""
    with _state_lock:
        state = _read_state_unlocked()
        pipeline = dict(state.get("pipeline") or {})
        pipeline["last_action"] = str(action or "").strip()
        pipeline["last_persisted_count"] = max(0, int(persisted_count))
        pipeline["last_synced_at"] = int(synced_at if synced_at is not None else time.time())
        state["pipeline"] = pipeline
        _write_state_unlocked(state)


def get_last_pipeline_persisted() -> dict:
    pipeline = load_state().get("pipeline") or {}
    action = str(pipeline.get("last_action") or "").strip()
    try:
        persisted_count = int(pipeline.get("last_persisted_count") or 0)
    except (TypeError, ValueError):
        persisted_count = 0
    if persisted_count < 0:
        persisted_count = 0
    synced_at = pipeline.get("last_synced_at")
    try:
        synced_at = int(synced_at) if synced_at else None
    except (TypeError, ValueError):
        synced_at = None
    if synced_at is not None and synced_at <= 0:
        synced_at = None
    return {
        "action": action,
        "persisted_count": persisted_count,
        "synced_at": synced_at,
    }
