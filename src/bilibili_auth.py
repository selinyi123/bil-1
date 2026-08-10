from __future__ import annotations

import os
import re

from src.bilibili_client import _load_cookie_string

_CSRF_RE = re.compile(r"(?:^|;\s*)bili_jct=([^;]+)")
_UID_RE = re.compile(r"(?:^|;\s*)DedeUserID=(\d+)")


def _parse_uid(cookie_str: str | None) -> int | None:
    if not cookie_str:
        return None
    match = _UID_RE.search(cookie_str)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def get_csrf_token() -> str | None:
    cookie = _load_cookie_string()
    if not cookie:
        return None
    match = _CSRF_RE.search(cookie)
    return match.group(1) if match else None


def get_login_uid() -> int | None:
    """当前请求 Cookie（BILI_COOKIE env > cookies.txt）解析出的 uid。"""
    return _parse_uid(_load_cookie_string())


def resolve_effective_uid() -> int | None:
    """解析当前生效身份 uid——UI 显示与实际请求身份必须一致（P1 #3）。

    优先级：
    1. `BILI_COOKIE` 环境变量（显式注入，覆盖一切；解析不出 uid 视为无身份）；
    2. 账号池活跃账号（config/accounts/active 文件）；
    3. `cookies.txt` 解析（旧版单账号路径）。

    注意：第二级延迟 import src.account_pool（避免模块级循环依赖，
    account_pool.get_active_uid 反向延迟 import 本函数）。
    """
    env = os.environ.get("BILI_COOKIE", "").strip()
    if env:
        return _parse_uid(env)
    from src.account_pool import pool_active_uid

    uid = pool_active_uid()
    if uid is not None:
        return uid
    return get_login_uid()


def require_login() -> tuple[str, int]:
    csrf = get_csrf_token()
    uid = get_login_uid()
    if not csrf or not uid:
        raise RuntimeError("未检测到有效登录 Cookie，请先运行 python scripts/bili_login.py")
    return csrf, uid
