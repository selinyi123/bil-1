from __future__ import annotations

from pathlib import Path
from typing import Any

from src.bilibili_client import BilibiliClient
from src.bilibili_login import COOKIE_PATH

NAV_URL = "https://api.bilibili.com/x/web-interface/nav"
NAV_STAT_URL = "https://api.bilibili.com/x/web-interface/nav/stat"
UNREAD_URL = "https://api.vc.bilibili.com/session_svr/v1/session_svr/single_unread"


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
                "unread_messages": None,
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
                unread_payload = client.request_json(
                    UNREAD_URL,
                    params={"build": 0, "mobi_app": "web"},
                    referer="https://www.bilibili.com",
                    retries=1,
                )
                if _api_code(unread_payload) == 0:
                    unread = unread_payload.get("data") or {}
                    profile["unread_messages"] = int(unread.get("follow_unread") or 0) + int(
                        unread.get("unfollow_unread") or 0
                    )
            except RuntimeError:
                pass

            return profile
    except RuntimeError as exc:
        empty["message"] = str(exc)
        return empty
