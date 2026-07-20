from __future__ import annotations

from src.log_redact import redact_obj, redact_text


def test_redact_sessdata_and_bearer() -> None:
    text = "cookie SESSDATA=abc123secret; bili_jct=xyz Bearer tok_value_here"
    out = redact_text(text)
    assert "abc123secret" not in out
    assert "SESSDATA=***" in out
    assert "Bearer ***" in out
    assert "bili_jct=***" in out


def test_redact_api_key_line() -> None:
    text = "LLM_API_KEY=sk-not-real-key-12345 saved"
    out = redact_text(text)
    assert "sk-not-real-key-12345" not in out
    assert "LLM_API_KEY=***" in out


def test_redact_keeps_normal_chinese() -> None:
    text = "一键更新完成：新链接 3 条，入库 2 条"
    assert redact_text(text) == text


def test_redact_obj_secret_keys() -> None:
    payload = {"api_key": "secret", "message": "ok", "nested": {"password": "p@ss"}}
    out = redact_obj(payload)
    assert out["api_key"] == "***"
    assert out["message"] == "ok"
    assert out["nested"]["password"] == "***"
