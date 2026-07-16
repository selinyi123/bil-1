from __future__ import annotations

from src.lottery_enricher import _lottery_time_from_llm_parse
from src.lottery_time import SIX_MONTHS_SECONDS


def test_lottery_time_from_llm_parse_uses_unix_only() -> None:
    unix, conditions = _lottery_time_from_llm_parse(
        {
            "lottery_time_text": "2026年7月8日",
            "lottery_time_unix": 1783440000,
        }
    )
    assert unix == 1783440000
    assert conditions["lottery_time_text"] == "2026年7月8日"
    assert "lottery_time_inferred" not in conditions


def test_lottery_time_from_llm_parse_no_local_fallback_for_text() -> None:
    unix, conditions = _lottery_time_from_llm_parse(
        {
            "lottery_time_text": "2026年7月8日",
            "lottery_time_unix": None,
        }
    )
    assert conditions["lottery_time_text"] == "2026年7月8日"
    assert conditions.get("lottery_time_inferred") is True
    assert unix > 1_000_000_000


def test_lottery_time_from_llm_parse_default_when_empty() -> None:
    unix, conditions = _lottery_time_from_llm_parse(
        {"lottery_time_text": "", "lottery_time_unix": None}
    )
    assert conditions.get("lottery_time_inferred") is True
    assert "lottery_time_text" in conditions
