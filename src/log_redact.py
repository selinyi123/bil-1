"""日志与诊断包脱敏（写入时与导出时复用）。"""

from __future__ import annotations

import re
from typing import Any

from src.secrets_inventory import is_redact_secret_key

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(SESSDATA=)[^\s;|&]+", re.IGNORECASE), r"\1***"),
    (re.compile(r"(bili_jct=)[^\s;|&]+", re.IGNORECASE), r"\1***"),
    (re.compile(r"(DedeUserID=)[^\s;|&]+", re.IGNORECASE), r"\1***"),
    (re.compile(r"(Bearer\s+)\S+", re.IGNORECASE), r"\1***"),
    (re.compile(r"(LLM_API_KEY\s*=\s*)\S+", re.IGNORECASE), r"\1***"),
    (re.compile(r"(api[_-]?key\s*[=:]\s*)\S+", re.IGNORECASE), r"\1***"),
    (re.compile(r"(Authorization\s*:\s*)\S+", re.IGNORECASE), r"\1***"),
    # 长 JWT / base64 块
    (re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"), "***"),
    (re.compile(r"\b[A-Za-z0-9+/]{80,}={0,2}\b"), "***"),
]


def redact_text(text: str) -> str:
    if not text:
        return text or ""
    out = str(text)
    for pattern, repl in _PATTERNS:
        out = pattern.sub(repl, out)
    return out


def redact_obj(obj: Any) -> Any:
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    if isinstance(obj, str):
        return redact_text(obj)
    if isinstance(obj, dict):
        cleaned: dict[str, Any] = {}
        for key, value in obj.items():
            key_s = str(key)
            if is_redact_secret_key(key_s):
                cleaned[key_s] = "***"
            else:
                cleaned[key_s] = redact_obj(value)
        return cleaned
    if isinstance(obj, (list, tuple)):
        return [redact_obj(item) for item in obj]
    try:
        return redact_text(str(obj))
    except Exception:
        return "<unserializable>"
