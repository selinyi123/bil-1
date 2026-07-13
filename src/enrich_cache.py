from __future__ import annotations

import json
import threading
from pathlib import Path

from src.state_store import DATA_DIR

CACHE_PATH = DATA_DIR / "cache" / "enrich_cache.json"
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


def get_cached_entry(dynamic_id: str) -> dict | None:
    entry = load_cache().get(dynamic_id)
    return entry if isinstance(entry, dict) else None


def save_cache(entries: dict[str, dict]) -> Path:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps({"entries": entries}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return CACHE_PATH


def merge_cache(updates: dict[str, dict]) -> Path:
    with _lock:
        entries = load_cache()
        entries.update(updates)
        return save_cache(entries)


def remove_cache_entries(dynamic_ids: list[str]) -> None:
    if not dynamic_ids:
        return
    with _lock:
        entries = load_cache()
        changed = False
        for dynamic_id in dynamic_ids:
            if dynamic_id in entries:
                del entries[dynamic_id]
                changed = True
        if changed:
            save_cache(entries)
