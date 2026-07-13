from __future__ import annotations

from unittest.mock import patch

from src.bilibili_login import POLL_SCANNED, POLL_SUCCESS, POLL_WAITING, login_with_qrcode


def test_login_status_change_on_scan_and_confirm() -> None:
    phases: list[tuple[str, str]] = []
    poll_responses = [
        {"data": {"code": POLL_WAITING}},
        {"data": {"code": POLL_SCANNED}},
        {"data": {"code": POLL_SUCCESS, "url": ""}},
    ]

    class FakeResponse:
        def __init__(self, payload: dict):
            self._payload = payload
            self.headers = {}

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self._payload

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.cookies = type("Jar", (), {"jar": []})()

        def get(self, url, **kwargs):
            if "generate" in url:
                return FakeResponse({"code": 0, "data": {"url": "https://example.com", "qrcode_key": "k1"}})
            if "poll" in url:
                return FakeResponse(poll_responses.pop(0))
            return FakeResponse({"code": 0})

        def close(self) -> None:
            return None

    with (
        patch("src.bilibili_login.httpx.Client", FakeClient),
        patch("src.bilibili_login._generate_qrcode_image", return_value=True),
        patch("src.bilibili_login._collect_login_cookies", return_value={"SESSDATA": "x", "bili_jct": "y"}),
        patch("src.bilibili_login.save_cookies", return_value=None),
    ):
        login_with_qrcode(
            open_image=False,
            timeout=10,
            on_status_change=lambda phase, message: phases.append((phase, message)),
        )

    assert ("waiting", "请使用哔哩哔哩 App 扫描二维码") in phases
    assert ("scanned", "扫码成功，请在手机上点击「确认登录」") in phases
    assert ("confirming", "已确认，正在完成登录…") in phases
    assert ("success", "登录成功") in phases
