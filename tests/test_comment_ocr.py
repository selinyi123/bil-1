"""评论验证码 OCR（P1）回归测试：12015 验证码 → OCR 识别 → 带 code 重发。"""
from __future__ import annotations

from src.lottery_actions import (
    CAPTCHA_REQUIRED_CODE,
    CAPTCHA_WRONG_CODE,
    _ocr_recognize,
    comment_dynamic,
)


class _FakeClient:
    def __init__(self, responses: list[tuple[int, dict]]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def post_form(self, url, data, *, referer=None, raise_on_code=False, retries=3):
        self.calls.append(dict(data))
        code, data_dict = self.responses.pop(0)
        payload = {"code": code, "message": "ok", "data": data_dict}
        return payload


def test_comment_ok_without_captcha(monkeypatch) -> None:
    called = {"ocr": 0}

    def fake_ocr(url):
        called["ocr"] += 1
        return "1234"

    monkeypatch.setattr("src.lottery_actions._ocr_recognize", fake_ocr)
    client = _FakeClient([(0, {})])
    result = comment_dynamic(
        client, rid="100", comment_type=17, message="好运连连！", csrf="cs", referer="http://r"
    )
    assert result.ok is True
    assert called["ocr"] == 0  # 正常评论不触发 OCR
    assert "code" not in client.calls[0]


def test_comment_ocr_success(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.lottery_actions._ocr_recognize", lambda url: "ab12"
    )
    client = _FakeClient([(CAPTCHA_REQUIRED_CODE, {"url": "http://cap"}), (0, {})])
    # 第一次返回 12015（需要验证码）+ 验证码图片 url，第二次带 code 重发成功
    result = comment_dynamic(
        client, rid="100", comment_type=17, message="好运连连！", csrf="cs", referer="http://r"
    )
    assert result.ok is True
    assert client.calls[1]["code"] == "ab12"


def test_comment_ocr_retries_wrong_code(monkeypatch) -> None:
    calls = {"n": 0}

    def fake_ocr(url):
        calls["n"] += 1
        return "0000"

    monkeypatch.setattr("src.lottery_actions._ocr_recognize", fake_ocr)
    client = _FakeClient(
        [
            (CAPTCHA_REQUIRED_CODE, {"url": "http://cap"}),
            (CAPTCHA_WRONG_CODE, {}),
            (0, {}),
        ]
    )
    result = comment_dynamic(
        client, rid="100", comment_type=17, message="好运连连！", csrf="cs", referer="http://r"
    )
    assert result.ok is True
    assert calls["n"] == 2  # 识别了两次


def test_comment_ocr_unavailable_fails(monkeypatch) -> None:
    monkeypatch.setattr("src.lottery_actions._ocr_recognize", lambda url: None)
    client = _FakeClient([(CAPTCHA_REQUIRED_CODE, {"url": "http://cap"})])
    result = comment_dynamic(
        client, rid="100", comment_type=17, message="好运连连！", csrf="cs", referer="http://r"
    )
    assert result.ok is False
    assert "验证码" in result.detail


def test_ocr_recognize_missing_endpoint_returns_none(monkeypatch) -> None:
    monkeypatch.setattr("src.lottery_actions.os.environ", {})
    # 未配置 OCR 服务（使用默认端点且不可达）→ 返回 None
    assert _ocr_recognize("http://cap") is None
