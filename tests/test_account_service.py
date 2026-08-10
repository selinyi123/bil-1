from __future__ import annotations

from unittest.mock import patch

from web.account_service import _api_code, _profile_from_network_error, get_account_profile, has_login_cookie
from web.user_messages import friendly_network_error


def test_friendly_network_error_masks_ssl_timeout() -> None:
    msg = friendly_network_error("网络请求失败: _ssl.c:999: The handshake operation timed out")
    assert "B 站" in msg
    assert "_ssl" not in msg


def test_profile_from_network_error_uses_cookie_and_cache(monkeypatch) -> None:
    monkeypatch.setattr("web.account_service.resolve_effective_uid", lambda: 12345)
    monkeypatch.setattr(
        "web.account_service._load_account_cache",
        lambda uid: {"uname": "cached_user", "mid": 999},
    )
    profile = _profile_from_network_error(RuntimeError("网络请求失败: handshake timed out"))
    assert profile["network_error"] is True
    assert profile["cookie_saved"] is True
    assert profile["mid"] == 999
    assert profile["uname"] == "cached_user"
    assert "B 站" in profile["message"]


def test_profile_from_network_error_cache_keyed_by_current_uid(monkeypatch) -> None:
    """核心不变量：网络失败回退缓存必须按当前 uid 查询，绝不串号。"""
    monkeypatch.setattr("web.account_service.resolve_effective_uid", lambda: 12345)
    seen_uids: list[int] = []
    monkeypatch.setattr(
        "web.account_service._load_account_cache",
        lambda uid: seen_uids.append(uid) or {},
    )
    profile = _profile_from_network_error(RuntimeError("网络请求失败: handshake timed out"))
    assert seen_uids == [12345]
    # 缓存无当前账号记录 → 不展示任何他人资料
    assert profile["mid"] == 12345
    assert profile["uname"] == ""


def test_api_code_handles_non_numeric() -> None:
    assert _api_code({"code": "oops"}) == -1
    assert _api_code({"code": None}) == -1
    assert _api_code({"code": 0}) == 0


def test_get_account_profile_without_cookie_is_instant(tmp_path, monkeypatch) -> None:
    cookie_path = tmp_path / "cookies.txt"
    monkeypatch.setattr("src.app_paths.cookie_file", lambda: cookie_path)
    monkeypatch.delenv("BILI_COOKIE", raising=False)  # 防 CI 环境残留 env cookie

    profile = get_account_profile()
    assert profile["logged_in"] is False
    assert "扫码登录" in profile["message"]
    assert profile["extras_loading"] is False


def test_has_login_cookie_true_with_env_cookie_only(tmp_path, monkeypatch) -> None:
    """P1 #3：仅有 BILI_COOKIE（无 cookies.txt 文件）也视为已登录。"""
    cookie_path = tmp_path / "cookies.txt"
    monkeypatch.setattr("src.app_paths.cookie_file", lambda: cookie_path)
    monkeypatch.setenv("BILI_COOKIE", "SESSDATA=x; bili_jct=y; DedeUserID=1001")
    assert has_login_cookie() is True
    assert not cookie_path.exists()  # 文件确实不存在


def test_has_login_cookie_false_without_env_or_file(tmp_path, monkeypatch) -> None:
    cookie_path = tmp_path / "cookies.txt"
    monkeypatch.setattr("src.app_paths.cookie_file", lambda: cookie_path)
    monkeypatch.delenv("BILI_COOKIE", raising=False)
    assert has_login_cookie() is False

    cookie_path.write_text("DedeUserID=1", encoding="utf-8")
    assert has_login_cookie() is False  # 文件存在但不含 SESSDATA

    cookie_path.write_text("SESSDATA=x", encoding="utf-8")
    assert has_login_cookie() is True


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
