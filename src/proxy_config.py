"""代理配置（源自 LAS 的 PROXY_HOST 机制，适配 httpx）。

优先级：环境变量 `BINGGO_PROXY` > `config/proxy.json`（支持键 url/http/https/proxy）。
返回形如 `http://user:pass@host:port` 的代理 URL，未配置返回 None。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from src.app_paths import config_dir

PROXY_ENV = "BINGGO_PROXY"
_PROXY_JSON = "proxy.json"
_cache: dict | None = None


def _load_json() -> dict:
    global _cache
    if _cache is None:
        try:
            path: Path = config_dir() / _PROXY_JSON
            _cache = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except Exception:
            _cache = {}
    return _cache


def get_proxy_url() -> str | None:
    """返回当前代理 URL；未配置返回 None。"""
    env = os.environ.get(PROXY_ENV, "").strip()
    if env:
        return env
    cfg = _load_json()
    for key in ("url", "http", "https", "proxy"):
        value = str(cfg.get(key) or "").strip()
        if value:
            return value
    return None
