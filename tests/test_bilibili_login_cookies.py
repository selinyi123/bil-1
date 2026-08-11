from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.bilibili_login import _collect_login_cookies


def test_collect_login_cookies_visits_cross_url_before_returning() -> None:
    visited: list[str] = []

    class FakeCookie:
        def __init__(self, name: str, value: str, domain: str = ".bilibili.com"):
            self.name = name
            self.value = value
            self.domain = domain

    class FakeClient:
        cookies = type("Jar", (), {"jar": [FakeCookie("SESSDATA", "old"), FakeCookie("bili_jct", "old")]})()

        def get(self, url: str, **kwargs):
            visited.append(url)
            if "sso" in url or "bilibili.com/cross" in url:
                self.cookies.jar.append(FakeCookie("SESSDATA", "new_session"))
                self.cookies.jar.append(FakeCookie("bili_jct", "new_csrf"))
            return MagicMock()

    poll = MagicMock()
    poll.headers = MagicMock()
    poll.headers.get_list = MagicMock(return_value=[])
    body = {"data": {"url": "https://passport.bilibili.com/x/passport-login/web/cross/sso?foo=1"}}

    cookies = _collect_login_cookies(FakeClient(), poll, body)

    assert any("cross" in url or "sso" in url for url in visited)
    assert cookies.get("SESSDATA") == "new_session"


class _OkResp:
    """业务 code=0 的假响应。"""

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"code": 0, "data": {}}


def test_get_json_wbi_nav_failure_retries(monkeypatch) -> None:
    """#28：WBI 前置 nav 请求失败（_ensure_wbi_keys 抛 RuntimeError）也参与 retry——
    首次失败、第二次成功后 get_json 正常返回（不再像旧实现那样绕过 retry 直接抛错）。"""
    from src.bilibili_client import BilibiliClient

    calls = {"ensure": 0}

    client = BilibiliClient(warmup=False)
    monkeypatch.setattr(client, "_http_get", lambda *args, **kwargs: _OkResp())
    monkeypatch.setattr("src.bilibili_client.time.sleep", lambda s: None)

    def fake_ensure():
        calls["ensure"] += 1
        if calls["ensure"] == 1:
            raise RuntimeError("nav 请求失败")
        # 签名密钥须 >= 64 字符，wbi_sign 的 MIXIN_KEY_ENC_TAB 会索引到 0..63
        client._img_key = "a" * 32
        client._sub_key = "b" * 32

    monkeypatch.setattr(client, "_ensure_wbi_keys", fake_ensure)

    try:
        result = client.get_json(
            "https://api.bilibili.com/x/space/wbi/arc/search",
            params={"mid": 1},
            wbi=True,
            retries=2,
        )
    finally:
        client.close()
    assert result == {"code": 0, "data": {}}
    assert calls["ensure"] == 2


def test_get_json_wbi_nav_failure_all_retries_exhausted_raises(monkeypatch) -> None:
    """#28：WBI 前置 nav 全部失败 → 最终抛 RuntimeError（不静默伪装成功）。"""
    from src.bilibili_client import BilibiliClient

    client = BilibiliClient(warmup=False)
    monkeypatch.setattr(client, "_http_get", lambda *args, **kwargs: _OkResp())
    monkeypatch.setattr("src.bilibili_client.time.sleep", lambda s: None)

    def fake_ensure():
        raise RuntimeError("nav 请求失败")

    monkeypatch.setattr(client, "_ensure_wbi_keys", fake_ensure)

    try:
        with pytest.raises(RuntimeError, match="nav 请求失败"):
            client.get_json(
                "https://api.bilibili.com/x/space/wbi/arc/search",
                params={"mid": 1},
                wbi=True,
                retries=1,
            )
    finally:
        client.close()

