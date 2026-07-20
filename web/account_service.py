from __future__ import annotations

from typing import Any

from src.bilibili_auth import get_login_uid
from src.bilibili_client import BilibiliClient
from src.message_api import get_unread_summary
from src.message_watch import BILIBILI_AT_NOTIFY_URL, acknowledge_at_unread, evaluate_at_unread_alert
from web.user_messages import friendly_network_error

NAV_URL = "https://api.bilibili.com/x/web-interface/nav"
NAV_STAT_URL = "https://api.bilibili.com/x/web-interface/nav/stat"
ACCOUNT_CLIENT_TIMEOUT = 8.0


def _api_code(payload: dict[str, Any]) -> int:
    code = payload.get("code")
    if code is None:
        return -1
    try:
        return int(code)
    except (TypeError, ValueError):
        return -1


def _empty_profile(message: str = "") -> dict[str, Any]:
    return {
        "logged_in": False,
        "expired": True,
        "message": message,
        "uname": "",
        "face": "",
        "mid": None,
        "following": None,
        "dynamic_count": None,
        "unread_messages": None,
        "unread_at": None,
        "extras_loading": False,
        "at_alert": _default_at_alert(),
        "at_notify_url": BILIBILI_AT_NOTIFY_URL,
    }


def _default_at_alert(current: int = 0) -> dict[str, Any]:
    return {
        "increased": False,
        "delta": 0,
        "previous": 0,
        "current": current,
    }


def _load_account_cache() -> dict[str, Any]:
    from src.db.json_cols import loads_json
    from src.db.models import AccountProfileCacheRow
    from src.db.session import session_scope

    try:
        with session_scope() as session:
            row = session.get(AccountProfileCacheRow, 1)
            if row is None:
                return {}
            raw = loads_json(row.raw_json, default={})
            if isinstance(raw, dict) and raw:
                return raw
            return {
                key: getattr(row, key)
                for key in ("uname", "face", "mid", "following", "dynamic_count")
                if getattr(row, key) is not None
            }
    except Exception:
        return {}


def _save_account_cache(profile: dict[str, Any]) -> None:
    from src.db.json_cols import dumps_json
    from src.db.models import AccountProfileCacheRow
    from src.db.session import session_scope

    payload = {
        key: profile.get(key)
        for key in ("uname", "face", "mid", "following", "dynamic_count")
        if profile.get(key) is not None
    }
    if not payload:
        return
    try:
        import time

        with session_scope() as session:
            row = session.get(AccountProfileCacheRow, 1)
            now = int(time.time())
            if row is None:
                session.add(
                    AccountProfileCacheRow(
                        id=1,
                        uname=payload.get("uname"),
                        face=payload.get("face"),
                        mid=int(payload["mid"]) if payload.get("mid") is not None else None,
                        following=int(payload["following"])
                        if payload.get("following") is not None
                        else None,
                        dynamic_count=int(payload["dynamic_count"])
                        if payload.get("dynamic_count") is not None
                        else None,
                        updated_at=now,
                        raw_json=dumps_json(payload),
                    )
                )
            else:
                row.uname = payload.get("uname")
                row.face = payload.get("face")
                row.mid = int(payload["mid"]) if payload.get("mid") is not None else None
                row.following = (
                    int(payload["following"]) if payload.get("following") is not None else None
                )
                row.dynamic_count = (
                    int(payload["dynamic_count"])
                    if payload.get("dynamic_count") is not None
                    else None
                )
                row.updated_at = now
                row.raw_json = dumps_json(payload)
    except Exception:
        pass


def _profile_from_network_error(exc: RuntimeError) -> dict[str, Any]:
    profile = _empty_profile(friendly_network_error(str(exc)))
    profile["cookie_saved"] = True
    profile["network_error"] = True
    uid = get_login_uid()
    if uid:
        profile["mid"] = uid
    cached = _load_account_cache()
    for key in ("uname", "face", "following", "dynamic_count", "mid"):
        if cached.get(key) is not None:
            profile[key] = cached[key]
    return profile


def clear_login_cookie() -> None:
    from src import app_paths
    from src.secure_files import harden_file_permissions

    path = app_paths.cookie_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            path.unlink()
            return
        except OSError:
            path.write_text("", encoding="utf-8")
            harden_file_permissions(path)
    else:
        path.write_text("", encoding="utf-8")
        harden_file_permissions(path)


def has_login_cookie() -> bool:
    from src import app_paths

    path = app_paths.cookie_file()
    if not path.exists():
        return False
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    return bool(text) and "SESSDATA" in text


def get_account_profile() -> dict[str, Any]:
    """快速返回账号基础信息，不阻塞在私信/@ 未读接口上。"""
    if not has_login_cookie():
        return _empty_profile("请使用侧边栏扫码登录")

    try:
        with BilibiliClient(timeout=ACCOUNT_CLIENT_TIMEOUT, warmup=False) as client:
            nav_payload = client.request_json(
                NAV_URL,
                referer="https://www.bilibili.com",
                retries=0,
            )
            code = _api_code(nav_payload)
            data = nav_payload.get("data") or {}
            is_login = bool(data.get("isLogin"))
            if code == -101 or not is_login:
                return _empty_profile("Cookie 已过期，请重新扫码登录")

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
                "unread_at": None,
                "extras_loading": True,
                "at_alert": _default_at_alert(),
                "at_notify_url": BILIBILI_AT_NOTIFY_URL,
            }

            try:
                stat_payload = client.request_json(
                    NAV_STAT_URL,
                    params={"mid": mid} if mid else None,
                    referer="https://www.bilibili.com",
                    retries=0,
                )
                if _api_code(stat_payload) == 0:
                    stat = stat_payload.get("data") or {}
                    profile["following"] = int(stat.get("following") or 0)
                    profile["dynamic_count"] = int(stat.get("dynamic_count") or 0)
            except RuntimeError:
                pass

            _save_account_cache(profile)
            return profile
    except RuntimeError as exc:
        if has_login_cookie():
            return _profile_from_network_error(exc)
        return _empty_profile(friendly_network_error(str(exc)))


def get_account_extras() -> dict[str, Any]:
    """补充私信/@ 未读与提醒，供前端后台加载。"""
    if not has_login_cookie():
        raise RuntimeError("未登录，请先扫码登录")

    uid = get_login_uid()
    extras: dict[str, Any] = {
        "unread_messages": 0,
        "unread_at": 0,
        "extras_loading": False,
        "at_alert": _default_at_alert(),
        "at_notify_url": BILIBILI_AT_NOTIFY_URL,
    }

    try:
        with BilibiliClient(timeout=ACCOUNT_CLIENT_TIMEOUT, warmup=False) as client:
            unread_summary = get_unread_summary(client, retries=0)
            extras["unread_messages"] = unread_summary.get("dm", 0)
            extras["unread_at"] = unread_summary.get("at", 0)
            extras["unread_by_type"] = unread_summary
    except RuntimeError:
        pass

    if uid:
        try:
            alert = evaluate_at_unread_alert(uid, int(extras.get("unread_at") or 0))
            extras["at_alert"] = alert.to_dict()
        except OSError:
            extras["at_alert"] = _default_at_alert(int(extras.get("unread_at") or 0))

    return extras


def ack_at_unread_notice(current: int) -> dict[str, Any]:
    uid = get_login_uid()
    if not uid:
        raise RuntimeError("未登录，请先扫码登录")
    baseline = acknowledge_at_unread(uid, current)
    alert = evaluate_at_unread_alert(uid, current)
    return {
        "acknowledged": True,
        "last_seen_unread_at": baseline,
        "at_alert": alert.to_dict(),
        "at_notify_url": BILIBILI_AT_NOTIFY_URL,
    }
