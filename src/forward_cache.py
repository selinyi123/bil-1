"""转发动态解析 / 分类结果缓存（两张表共用一套读写，按 row 模型区分）。

ForwardParseCacheRow 与 ForwardClassifyCacheRow 字段完全一致
（dynamic_id / content_hash / parsed_json / updated_at），故只保留一份实现。
"""

from __future__ import annotations

import hashlib
import re
import threading
import time

from sqlmodel import select

from src.db.json_cols import dumps_json, loads_json
from src.db.models import ForwardClassifyCacheRow, ForwardParseCacheRow
from src.db.session import session_scope

_lock = threading.Lock()


def _content_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip())
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()


def load_cache(row_model: type) -> dict[str, dict]:
    with session_scope() as session:
        out: dict[str, dict] = {}
        for row in session.exec(select(row_model)).all():
            out[row.dynamic_id] = {
                "content_hash": row.content_hash,
                "parsed": loads_json(row.parsed_json, {}),
            }
        return out


def get_cached(row_model: type, dynamic_id: str, content_text: str) -> dict | None:
    with session_scope() as session:
        row = session.get(row_model, str(dynamic_id))
        if row is None:
            return None
        if row.content_hash != _content_hash(content_text):
            return None
        parsed = loads_json(row.parsed_json, None)
        return parsed if isinstance(parsed, dict) else None


def put_cached(row_model: type, dynamic_id: str, content_text: str, parsed: dict) -> None:
    with _lock:
        now = int(time.time())
        with session_scope() as session:
            row = session.get(row_model, str(dynamic_id))
            if row is None:
                session.add(
                    row_model(
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


def load_parse_cache() -> dict[str, dict]:
    return load_cache(ForwardParseCacheRow)


def load_classify_cache() -> dict[str, dict]:
    return load_cache(ForwardClassifyCacheRow)


def get_cached_parse(dynamic_id: str, content_text: str) -> dict | None:
    return get_cached(ForwardParseCacheRow, dynamic_id, content_text)


def put_cached_parse(dynamic_id: str, content_text: str, parsed: dict) -> None:
    put_cached(ForwardParseCacheRow, dynamic_id, content_text, parsed)


def get_cached_classify(dynamic_id: str, content_text: str) -> dict | None:
    return get_cached(ForwardClassifyCacheRow, dynamic_id, content_text)


def put_cached_classify(dynamic_id: str, content_text: str, parsed: dict) -> None:
    put_cached(ForwardClassifyCacheRow, dynamic_id, content_text, parsed)
