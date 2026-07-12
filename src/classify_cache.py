from __future__ import annotations

import json
import threading
from pathlib import Path

from src.state_store import DATA_DIR

CACHE_PATH = DATA_DIR / "cache" / "classify_cache.json"
_lock = threading.Lock()


def load_cache() -> dict[str, dict]:
    if not CACHE_PATH.exists():
        return {}
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    entries = data.get("entries") or {}
    return entries if isinstance(entries, dict) else {}


def get_cached_type(dynamic_id: str) -> str | None:
    entry = load_cache().get(dynamic_id)
    if not entry:
        return None
    lottery_type = entry.get("lottery_type")
    return lottery_type if isinstance(lottery_type, str) else None


def save_cache(entries: dict[str, dict]) -> Path:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"entries": entries}
    CACHE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return CACHE_PATH


def put_cache(dynamic_id: str, lottery_type: str, *, classified_at: int) -> None:
    with _lock:
        entries = load_cache()
        entries[dynamic_id] = {
            "lottery_type": lottery_type,
            "classified_at": classified_at,
        }
        save_cache(entries)


def merge_cache(updates: dict[str, dict]) -> Path:
    with _lock:
        entries = load_cache()
        entries.update(updates)
        return save_cache(entries)
