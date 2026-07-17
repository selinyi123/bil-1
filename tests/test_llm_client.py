from __future__ import annotations

from src.llm_client import _build_chat_payload
from src.llm_config import LlmConfig


def test_build_chat_payload_disables_deepseek_thinking() -> None:
    config = LlmConfig(
        api_key="k",
        base_url="https://api.deepseek.com",
        model_name="deepseek-v4-flash",
    )
    payload = _build_chat_payload(
        config,
        messages=[{"role": "user", "content": "ping"}],
    )
    assert payload["thinking"] == {"type": "disabled"}


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
