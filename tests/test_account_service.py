from __future__ import annotations

from unittest.mock import patch

from web.account_service import _api_code, _profile_from_network_error, get_account_profile, has_login_cookie
from web.user_messages import friendly_network_error


def test_friendly_network_error_masks_ssl_timeout() -> None:
    msg = friendly_network_error("网络请求失败: _ssl.c:999: The handshake operation timed out")
    assert "B 站" in msg
    assert "_ssl" not in msg


def test_profile_from_network_error_uses_cookie_and_cache(monkeypatch) -> None:
    monkeypatch.setattr("web.account_service.get_login_uid", lambda: 12345)
    monkeypatch.setattr(
        "web.account_service._load_account_cache",
        lambda: {"uname": "cached_user", "mid": 999},
    )
    profile = _profile_from_network_error(RuntimeError("网络请求失败: handshake timed out"))
    assert profile["network_error"] is True
    assert profile["cookie_saved"] is True
    assert profile["mid"] == 999
    assert profile["uname"] == "cached_user"
    assert "B 站" in profile["message"]


def test_api_code_handles_non_numeric() -> None:
    assert _api_code({"code": "oops"}) == -1
    assert _api_code({"code": None}) == -1
    assert _api_code({"code": 0}) == 0


def test_get_account_profile_without_cookie_is_instant(tmp_path, monkeypatch) -> None:
    import web.account_service as account_service

    cookie_path = tmp_path / "cookies.txt"
    monkeypatch.setattr(account_service, "COOKIE_PATH", cookie_path)

    profile = get_account_profile()
    assert profile["logged_in"] is False
    assert "扫码登录" in profile["message"]
    assert profile["extras_loading"] is False


def test_get_account_profile_logged_in_shape(monkeypatch) -> None:
    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def request_json(self, url, params=None, *, referer=None, retries=0):
            if "nav/stat" in url:
                return {"code": 0, "data": {"following": 10, "dynamic_count": 3}}
            return {
                "code": 0,
                "data": {
                    "isLogin": True,
                    "mid": 123,
                    "uname": "tester",
                    "face": "https://example.com/a.jpg",
                },
            }

    monkeypatch.setattr("web.account_service.has_login_cookie", lambda: True)
    with patch("web.account_service.BilibiliClient", FakeClient):
        profile = get_account_profile()

    assert profile["logged_in"] is True
    assert profile["uname"] == "tester"
    assert profile["following"] == 10
    assert profile["extras_loading"] is True
    assert profile["unread_at"] is None
