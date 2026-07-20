from __future__ import annotations

import hashlib
import re
import threading
import time

from sqlmodel import select

from src.app_paths import DATA_DIR
from src.db.json_cols import dumps_json, loads_json
from src.db.models import ForwardClassifyCacheRow
from src.db.session import session_scope

CACHE_PATH = DATA_DIR / "cache" / "forward_classify_cache.json"
_lock = threading.Lock()


def _content_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip())
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()


def load_cache() -> dict[str, dict]:
    with session_scope() as session:
        out: dict[str, dict] = {}
        for row in session.exec(select(ForwardClassifyCacheRow)).all():
            out[row.dynamic_id] = {
                "content_hash": row.content_hash,
                "parsed": loads_json(row.parsed_json, {}),
            }
        return out


def get_cached_classify(dynamic_id: str, content_text: str) -> dict | None:
    with session_scope() as session:
        row = session.get(ForwardClassifyCacheRow, str(dynamic_id))
        if row is None:
            return None
        if row.content_hash != _content_hash(content_text):
            return None
        parsed = loads_json(row.parsed_json, None)
        return parsed if isinstance(parsed, dict) else None


def put_cached_classify(dynamic_id: str, content_text: str, parsed: dict) -> None:
    with _lock:
        now = int(time.time())
        with session_scope() as session:
            row = session.get(ForwardClassifyCacheRow, str(dynamic_id))
            if row is None:
                session.add(
                    ForwardClassifyCacheRow(
                        dynamic_id=str(dynamic_id),
                        content_hash=_content_hash(content_text),
                        parsed_json=dumps_json(parsed),
                        updated_at=now,
                    )
                )
            else:
                row.content_hash = _content_hash(content_text)
                row.parsed_json = dumps_json(parsed)
                row.updated_at = now
