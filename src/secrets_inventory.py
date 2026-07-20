"""敏感配置权威清单（F1）：供 redact / sanitize / diagnostics / 自检共用。

刻意保留差异：
- redact：全键名匹配（is_redact_secret_key）
- sanitize：子串匹配（is_sanitize_secret_key），更严，会丢弃 my_cookie 一类键
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from src import app_paths

SECRET_FILENAMES: frozenset[str] = frozenset(
    {
        "cookies.txt",
        "llm.env",
    }
)

SECRET_ENV_VARS: frozenset[str] = frozenset(
    {
        "BILI_COOKIE",
        "LLM_API_KEY",
    }
)

CONFIG_OVERRIDE_ENV_VARS: frozenset[str] = frozenset(
    {
        "BILI_COOKIE",
        "LLM_API_KEY",
        "LLM_BASE_URL",
        "LLM_MODEL_NAME",
    }
)

REDACT_SECRET_KEY_NAMES: frozenset[str] = frozenset(
    {
        "cookie",
        "token",
        "secret",
        "password",
        "authorization",
        "api_key",
        "api-key",
    }
)

SANITIZE_SECRET_KEY_SUBSTR: frozenset[str] = frozenset(
    {
        "cookie",
        "token",
        "secret",
        "password",
        "authorization",
        "api_key",
        "api-key",
    }
)


def secret_file_paths() -> list[Path]:
    """运行态密钥文件绝对路径（动态解析，尊重 BINGGO_HOME）。"""
    return [app_paths.cookie_file(), app_paths.llm_env_file()]


def secret_filenames_csv() -> str:
    return ",".join(sorted(SECRET_FILENAMES))


def is_redact_secret_key(name: str) -> bool:
    key = str(name or "").strip().lower()
    if not key:
        return False
    if key in REDACT_SECRET_KEY_NAMES:
        return True
    # 与历史 api[_-]?key 全键匹配一致（如 apikey）
    return bool(re.fullmatch(r"api[_-]?key", key))


def is_sanitize_secret_key(name: str) -> bool:
    key = str(name or "").lower()
    if not key:
        return False
    # 与历史子串规则一致（含 my_cookie、x_api_key 等）
    return bool(re.search(r"cookie|token|secret|password|authorization|api[_-]?key", key))


@lru_cache(maxsize=1)
def redact_secret_key_re() -> re.Pattern[str]:
    """兼容旧调用：全键名匹配正则。"""
    return re.compile(r"(?i)^(cookie|token|secret|password|authorization|api[_-]?key)$")


@lru_cache(maxsize=1)
def sanitize_secret_key_re() -> re.Pattern[str]:
    """兼容旧调用：子串匹配正则。"""
    return re.compile(r"(?i)cookie|token|secret|password|authorization|api[_-]?key")
