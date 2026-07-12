from __future__ import annotations

import re

from src.bilibili_client import _load_cookie_string

_CSRF_RE = re.compile(r"(?:^|;\s*)bili_jct=([^;]+)")
_UID_RE = re.compile(r"(?:^|;\s*)DedeUserID=(\d+)")


def get_csrf_token() -> str | None:
    cookie = _load_cookie_string()
    if not cookie:
        return None
    match = _CSRF_RE.search(cookie)
    return match.group(1) if match else None


def get_login_uid() -> int | None:
    cookie = _load_cookie_string()
    if not cookie:
        return None
    match = _UID_RE.search(cookie)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def require_login() -> tuple[str, int]:
    csrf = get_csrf_token()
    uid = get_login_uid()
    if not csrf or not uid:
        raise RuntimeError("未检测到有效登录 Cookie，请先运行 python scripts/bili_login.py")
    return csrf, uid
