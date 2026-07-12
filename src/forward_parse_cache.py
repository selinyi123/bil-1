from __future__ import annotations

import hashlib
import json
import re
import threading
from pathlib import Path

from src.state_store import DATA_DIR

CACHE_PATH = DATA_DIR / "cache" / "forward_parse_cache.json"
_lock = threading.Lock()


def _content_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip())
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()


def load_cache() -> dict[str, dict]:
    if not CACHE_PATH.exists():
        return {}
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    entries = data.get("entries") or {}
    return entries if isinstance(entries, dict) else {}


def get_cached_parse(dynamic_id: str, content_text: str) -> dict | None:
    entry = load_cache().get(dynamic_id)
    if not entry:
        return None
    if entry.get("content_hash") != _content_hash(content_text):
        return None
    parsed = entry.get("parsed")
    return parsed if isinstance(parsed, dict) else None


def put_cached_parse(dynamic_id: str, content_text: str, parsed: dict) -> None:
    with _lock:
        entries = load_cache()
        entries[dynamic_id] = {
            "content_hash": _content_hash(content_text),
            "parsed": parsed,
        }
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(
            json.dumps({"entries": entries}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def merge_cache(updates: dict[str, dict]) -> None:
    with _lock:
        entries = load_cache()
        entries.update(updates)
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(
            json.dumps({"entries": entries}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
