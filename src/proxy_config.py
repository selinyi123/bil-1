"""代理配置（源自 LAS 的 PROXY_HOST 机制，适配 httpx）。

优先级：环境变量 `BINGGO_PROXY` > 账号级代理（`config/accounts/{uid}.json` 的
`proxy` 字段，仅在调用方传入 uid 时参与）> `config/proxy.json`（支持键
url/http/https/proxy）。返回形如 `http://user:pass@host:port` 的代理 URL，
未配置返回 None。

`proxy.json` 按文件 mtime 做缓存失效，改文件后无需重启即可热更新。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from src.app_paths import config_dir

PROXY_ENV = "BINGGO_PROXY"
_PROXY_JSON = "proxy.json"
_cache: dict | None = None
_cache_path: Path | None = None
_cache_mtime: float | None = None


def _load_json() -> dict:
    global _cache, _cache_path, _cache_mtime
    path: Path = config_dir() / _PROXY_JSON
    try:
        mtime = path.stat().st_mtime_ns if path.exists() else None
    except OSError:
        mtime = None
    if _cache is not None and _cache_path == path and _cache_mtime == mtime:
        return _cache
    try:
        _cache = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        _cache = {}
    _cache_path = path
    _cache_mtime = mtime
    return _cache


def get_env_proxy_url() -> str | None:
    """返回环境变量代理；未配置返回 None。"""
    value = os.environ.get(PROXY_ENV, "").strip()
    return value or None


def get_global_proxy_url() -> str | None:
    """只读取 proxy.json 的全局代理，不叠加环境变量/账号覆盖。"""
    cfg = _load_json()
    for key in ("url", "http", "https", "proxy"):
        value = str(cfg.get(key) or "").strip()
        if value:
            return value
    return None


def get_proxy_url(uid: int | None = None) -> str | None:
    """返回当前代理 URL；未配置返回 None。

    优先级：`BINGGO_PROXY` 环境变量 > 账号级代理（uid 非 None 时）> proxy.json。
    不带 uid 调用时跳过账号级代理，行为与旧版完全一致（向后兼容）。
    """
    env = get_env_proxy_url()
    if env:
        return env
    if uid is not None:
        from src.account_pool import get_account_proxy

        account_proxy = get_account_proxy(uid)
        if account_proxy:
            return account_proxy
    return get_global_proxy_url()
