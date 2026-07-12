from __future__ import annotations

import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
STATE_PATH = DATA_DIR / "state.json"


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"sources": {}}
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"sources": {}}
    state.setdefault("sources", {})
    return state


def save_state(state: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = STATE_PATH.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(STATE_PATH)


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
    state = load_state()
    entry = {
        "container_url": container_url,
        "container_id": container_id,
        "title": title,
        "checked_at": int(time.time()),
    }
    if cv_id is not None:
        entry["cv_id"] = cv_id
    state.setdefault("sources", {})[source_id] = entry
    save_state(state)
