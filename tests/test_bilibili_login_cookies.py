from __future__ import annotations

from unittest.mock import MagicMock

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
