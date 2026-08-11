"""通知推送（notify）测试。"""
from __future__ import annotations

import json

from src.notify import ALL_CHANNEL_NAMES, send_notify


def test_all_channels_skipped_without_credentials(isolated_home, monkeypatch) -> None:
    import src.notify as module

    config_dir = isolated_home / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "notify.json").write_text(json.dumps({"enabled": True, "channels": {}}), encoding="utf-8")
    monkeypatch.setattr(module, "config_dir", lambda: config_dir)
    module.reset_notify_config_cache()

    result = send_notify("标题", "内容")
    assert result["sent"] == []
    assert sorted(result["skipped"]) == sorted(ALL_CHANNEL_NAMES)


def test_send_sct_channel(isolated_home, monkeypatch) -> None:
    import httpx

    import src.notify as module

    config_dir = isolated_home / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "notify.json").write_text(
        json.dumps({"enabled": True, "channels": {"sct": {"sendkey": "KEY123"}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "config_dir", lambda: config_dir)
    module.reset_notify_config_cache()

    calls: list = []

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"code": 0}

    def fake_get(url, params=None, timeout=None):
        calls.append((url, params))
        return FakeResponse()

    monkeypatch.setattr(httpx, "get", fake_get)
    result = send_notify("标题", "内容")
    assert "sct" in result["sent"]
    url, params = calls[0]
    assert url == "https://sctapi.ftqq.com/KEY123.send"
    assert params["title"] == "标题"
    assert params["desp"] == "内容"


def test_sct_business_error_not_fake_success(isolated_home, monkeypatch) -> None:
    """Server酱业务错误（code!=0 不抛 HTTPError）不得记为发送成功。"""
    import httpx

    import src.notify as module

    config_dir = isolated_home / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "notify.json").write_text(
        json.dumps({"enabled": True, "channels": {"sct": {"sendkey": "KEY123"}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "config_dir", lambda: config_dir)
    module.reset_notify_config_cache()

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"code": 1024, "message": "invalid key"}

    monkeypatch.setattr(httpx, "get", lambda *a, **k: FakeResponse())
    result = send_notify("标题", "内容")
    assert "sct" not in result["sent"]
    assert "sct" in result["skipped"]


def test_telegram_http_401_not_fake_success(isolated_home, monkeypatch) -> None:
    """Telegram 401（HTTP 层失败）不得记为发送成功。"""
    import httpx

    import src.notify as module

    config_dir = isolated_home / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "notify.json").write_text(
        json.dumps(
            {"enabled": True, "channels": {"telegram": {"bot_token": "BAD", "chat_id": "1"}}}
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "config_dir", lambda: config_dir)
    module.reset_notify_config_cache()

    class FakeResponse:
        status_code = 401

        def json(self):
            return {"ok": False, "error_code": 401, "description": "Unauthorized"}

    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse())
    result = send_notify("标题", "内容")
    assert "telegram" not in result["sent"]
    assert "telegram" in result["skipped"]


def test_feishu_signature_correct(isolated_home, monkeypatch) -> None:
    """飞书官方签名：HMAC-SHA256(key=f"{timestamp}\\n{secret}", msg=空串) 再 Base64。

    固定向量按官方协议独立计算（key 是 timestamp\\nsecret，消息体为空），
    生产实现必须与之匹配；若把 key/msg 写反会得到 19021 sign match fail。
    """
    import base64
    import hashlib
    import hmac
    import time as time_mod

    import httpx

    import src.notify as module

    captured: dict = {}

    class FakeResponse:
        status_code = 200
        text = '{"code": 0}'

        def json(self):
            return {"code": 0}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr(httpx, "post", fake_post)
    # 固定时间戳，保证签名可复现
    monkeypatch.setattr(time_mod, "time", lambda: 1700000000)

    cfg = {"webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/x", "secret": "my-secret"}
    result = module._feishu(cfg, "标题", "内容")

    assert result == "feishu"
    payload = captured["json"]
    assert payload["timestamp"] == "1700000000"
    string_to_sign = "1700000000\nmy-secret"
    # 官方算法：HMAC 的 key 是 string_to_sign，消息为空字节串
    expected = base64.b64encode(
        hmac.new(string_to_sign.encode(), digestmod=hashlib.sha256).digest()
    ).decode()
    assert payload["sign"] == expected
    # 反向（错误）算法必须不匹配，防止回归到旧实现
    wrong = base64.b64encode(
        hmac.new(b"my-secret", string_to_sign.encode(), hashlib.sha256).digest()
    ).decode()
    assert payload["sign"] != wrong


def test_http_ok_malformed_business_code_fails_closed(isolated_home, monkeypatch) -> None:
    """provider 明确给了业务码但无法解析（如 code="ERROR"）→ 视为失败（fail-closed）。"""
    import httpx

    import src.notify as module

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"code": "ERROR", "message": "boom"}

    assert module._http_ok(FakeResponse(), ok_codes=(0,)) is False
    # 数字业务码正常判定不受影响
    class OkResponse:
        status_code = 200

        def json(self):
            return {"code": 0}

    assert module._http_ok(OkResponse(), ok_codes=(0,)) is True


def test_feishu_business_error_not_fake_success(isolated_home, monkeypatch) -> None:
    """飞书业务错误（code!=0 不抛 HTTPError）不得记为发送成功。"""
    import httpx

    import src.notify as module

    class FakeResponse:
        status_code = 200
        text = '{"code": 19001, "msg": "sign match fail"}'

        def json(self):
            return {"code": 19001, "msg": "sign match fail"}

    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse())
    cfg = {"webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/x", "secret": "s"}
    assert module._feishu(cfg, "标题", "内容") is None


def test_disabled_sends_nothing(isolated_home, monkeypatch) -> None:
    import src.notify as module

    config_dir = isolated_home / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "notify.json").write_text(json.dumps({"enabled": False, "channels": {"sct": {"sendkey": "K"}}}), encoding="utf-8")
    monkeypatch.setattr(module, "config_dir", lambda: config_dir)
    module.reset_notify_config_cache()

    result = send_notify("标题", "内容")
    assert result == {"sent": [], "skipped": []}
