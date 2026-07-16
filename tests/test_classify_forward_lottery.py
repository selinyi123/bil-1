from __future__ import annotations

from src.forward_parser import CLASSIFY_PARSER_VERSION, classify_forward_lottery


def test_classify_forward_lottery_uses_lightweight_prompt(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_chat_json(*, system: str, user: str, config=None):
        captured["system"] = system
        captured["user"] = user
        return {"is_lottery": True, "confidence": "high"}

    monkeypatch.setattr("src.forward_parser.chat_json", fake_chat_json)
    monkeypatch.setattr("src.forward_parser.get_cached_classify", lambda *args, **kwargs: None)

    parsed = classify_forward_lottery(
        "classify-lightweight-prompt-v2",
        "转发+关注，抽 3 人送月卡，足够长的正文用于轻量分类测试唯一文本",
    )
    assert parsed["is_lottery"] is True
    assert parsed["classify_parser_version"] == CLASSIFY_PARSER_VERSION
    assert '"prize_description"' not in captured["system"]
    assert "是否转发抽奖" in captured["system"]
    assert "参与行动" in captured["system"]
    assert "奖品依据" in captured["system"]


def test_classify_prompt_requires_participation_and_prize_rules() -> None:
    from src.forward_parser import CLASSIFY_SYSTEM_PROMPT, PARSE_SYSTEM_PROMPT

    for keyword in ("点赞", "转发", "关注", "收藏"):
        assert keyword in CLASSIFY_SYSTEM_PROMPT
        assert keyword in PARSE_SYSTEM_PROMPT
    assert "万粉" in CLASSIFY_SYSTEM_PROMPT
    assert "is_lottery=false" in PARSE_SYSTEM_PROMPT or "is_lottery=false" in CLASSIFY_SYSTEM_PROMPT


def test_classify_forward_lottery_empty_content_uses_llm(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_chat_json(*, system: str, user: str, config=None):
        captured["system"] = system
        captured["user"] = user
        return {"is_lottery": False, "confidence": "high"}

    monkeypatch.setattr("src.forward_parser.chat_json", fake_chat_json)
    monkeypatch.setattr("src.forward_parser.get_cached_classify", lambda *args, **kwargs: None)

    parsed = classify_forward_lottery("123", "")
    assert parsed["is_lottery"] is False
    assert parsed.get("error") is None
    assert "无正文" in captured["system"]
    assert "(无正文)" in captured["user"]

    monkeypatch.setattr("src.forward_parser.get_cached_classify", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "src.forward_parser.chat_json",
        lambda **kwargs: {"is_lottery": False, "confidence": "low"},
    )
    parsed_one = classify_forward_lottery("classify-one-char-v2", "转")
    assert parsed_one.get("error") is None
    assert parsed_one["is_lottery"] is False
