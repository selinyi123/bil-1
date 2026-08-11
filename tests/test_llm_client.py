from __future__ import annotations

import pytest

from src.llm_client import (
    _build_chat_payload,
    _extract_json_object,
    chat_json,
    # 别名避免 pytest 把生产 test_llm_connection（带 config 参数）当测试收集
    test_llm_connection as _prod_test_llm_connection,
)
from src.llm_config import LlmConfig


def _config() -> LlmConfig:
    return LlmConfig(
        api_key="k",
        base_url="https://api.deepseek.com",
        model_name="deepseek-v4-flash",
    )


def test_build_chat_payload_disables_deepseek_thinking() -> None:
    config = _config()
    payload = _build_chat_payload(
        config,
        messages=[{"role": "user", "content": "ping"}],
    )
    assert payload["thinking"] == {"type": "disabled"}


def test_build_chat_payload_disables_autodl_deepseek_v4_flash() -> None:
    config = LlmConfig(
        api_key="k",
        base_url="https://www.autodl.art/api/v1",
        model_name="DeepSeek-V4-Flash",
    )
    payload = _build_chat_payload(
        config,
        messages=[{"role": "user", "content": "ping"}],
        max_tokens=64,
    )
    assert payload["thinking"] == {"type": "disabled"}
    assert payload["max_tokens"] == 64


def test_build_chat_payload_skips_thinking_for_other_providers() -> None:
    config = LlmConfig(
        api_key="k",
        base_url="https://api.example.com/v1",
        model_name="gpt-4o-mini",
    )
    payload = _build_chat_payload(
        config,
        messages=[{"role": "user", "content": "ping"}],
    )
    assert "thinking" not in payload


def test_llm_connection_ok_with_valid_content(monkeypatch) -> None:
    def fake_post(*, url, headers, payload):
        return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setattr("src.llm_client._post_chat_completion", fake_post)
    assert _prod_test_llm_connection(_config()) == "deepseek-v4-flash @ https://api.deepseek.com"


def test_llm_connection_rejects_missing_content(monkeypatch) -> None:
    def fake_post(*, url, headers, payload):
        return {"choices": []}

    monkeypatch.setattr("src.llm_client._post_chat_completion", fake_post)
    with pytest.raises(RuntimeError, match=r"choices\[0\]\.message\.content"):
        _prod_test_llm_connection(_config())


def test_llm_connection_rejects_non_string_content(monkeypatch) -> None:
    def fake_post(*, url, headers, payload):
        return {"choices": [{"message": {"content": 42}}]}

    monkeypatch.setattr("src.llm_client._post_chat_completion", fake_post)
    with pytest.raises(RuntimeError, match=r"choices\[0\]\.message\.content"):
        _prod_test_llm_connection(_config())


def test_extract_json_object_picks_first_complete_object() -> None:
    text = (
        '先说明一下 {"is_lottery": true, "prize_description": "月卡"} '
        '后面还有别的对象 {"is_lottery": false}'
    )
    parsed = _extract_json_object(text)
    assert parsed == {"is_lottery": True, "prize_description": "月卡"}


def test_extract_json_object_handles_fenced_json() -> None:
    text = '```json\n{"is_lottery": true}\n```'
    assert _extract_json_object(text) == {"is_lottery": True}


def test_extract_json_object_raises_without_object() -> None:
    with pytest.raises(RuntimeError, match="无法解析为 JSON"):
        _extract_json_object("这里没有任何 JSON 对象")


def test_chat_json_extracts_once_without_parse_retry(monkeypatch) -> None:
    calls: list[str] = []

    def fake_post(*, url, headers, payload):
        return {"choices": [{"message": {"content": '{"is_lottery": true}'}}]}

    def fake_extract(text):
        calls.append(text)
        return {"is_lottery": True}

    monkeypatch.setattr("src.llm_client._post_chat_completion", fake_post)
    monkeypatch.setattr("src.llm_client._extract_json_object", fake_extract)
    result = chat_json(system="s", user="u", config=_config())
    assert result == {"is_lottery": True}
    # retry 已删除：对同一 content 只解析一次
    assert len(calls) == 1


def test_chat_json_rejects_missing_content(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.llm_client._post_chat_completion",
        lambda **kw: {"choices": []},
    )
    with pytest.raises(RuntimeError, match=r"choices\[0\]\.message\.content"):
        chat_json(system="s", user="u", config=_config())
