from __future__ import annotations

from pathlib import Path
from typing import Any

from src.bilibili_client import BilibiliClient
from src.bilibili_login import COOKIE_PATH
from src.message_api import get_unread_summary

NAV_URL = "https://api.bilibili.com/x/web-interface/nav"
NAV_STAT_URL = "https://api.bilibili.com/x/web-interface/nav/stat"


def _api_code(payload: dict[str, Any]) -> int:
    code = payload.get("code")
    if code is None:
        return -1
    return int(code)


def clear_login_cookie() -> None:
    COOKIE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if COOKIE_PATH.exists():
        try:
            COOKIE_PATH.unlink()
        except OSError:
            COOKIE_PATH.write_text("", encoding="utf-8")
    else:
        COOKIE_PATH.write_text("", encoding="utf-8")


def has_login_cookie() -> bool:
    if not COOKIE_PATH.exists():
        return False
    try:
        text = COOKIE_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    return bool(text) and "SESSDATA" in text


def get_account_profile() -> dict[str, Any]:
    empty = {
        "logged_in": False,
        "expired": True,
        "message": "",
        "uname": "",
        "face": "",
        "mid": None,
        "following": None,
        "dynamic_count": None,
        "unread_messages": None,
        "unread_at": None,
    }
    try:
        with BilibiliClient() as client:
            nav_payload = client.request_json(NAV_URL, referer="https://www.bilibili.com", retries=1)
            code = _api_code(nav_payload)
            data = nav_payload.get("data") or {}
            is_login = bool(data.get("isLogin"))
            if code == -101 or not is_login:
                empty["message"] = "Cookie 已过期，请重新扫码登录"
                return empty

            mid = int(data.get("mid") or 0) or None
            profile: dict[str, Any] = {
                "logged_in": True,
                "expired": False,
                "message": "已登录",
                "uname": str(data.get("uname") or ""),
                "face": str(data.get("face") or ""),
                "mid": mid,
                "following": None,
                "dynamic_count": None,
                "unread_messages": 0,
                "unread_at": 0,
            }

            try:
                stat_payload = client.request_json(
                    NAV_STAT_URL,
                    params={"mid": mid} if mid else None,
                    referer="https://www.bilibili.com",
                    retries=1,
                )
                if _api_code(stat_payload) == 0:
                    stat = stat_payload.get("data") or {}
                    profile["following"] = int(stat.get("following") or 0)
                    profile["dynamic_count"] = int(stat.get("dynamic_count") or 0)
            except RuntimeError:
                pass

            try:
                unread_summary = get_unread_summary(client)
                profile["unread_messages"] = unread_summary.get("dm", 0)
                profile["unread_at"] = unread_summary.get("at", 0)
                profile["unread_by_type"] = unread_summary
            except RuntimeError:
                profile["unread_messages"] = profile.get("unread_messages", 0)
                profile["unread_at"] = profile.get("unread_at", 0)

            return profile
    except RuntimeError as exc:
        empty["message"] = str(exc)
        return empty
