from __future__ import annotations

from datetime import datetime

from src.lottery_enricher import _lottery_time_from_llm_parse
from src.lottery_time import BEIJING_TZ, LOTTERY_TIME_DISPLAY_FMT, SIX_MONTHS_SECONDS


def test_lottery_time_from_llm_parse_uses_display_string() -> None:
    display = "2026-07-08 00:00"
    unix, conditions = _lottery_time_from_llm_parse({"lottery_time": display})
    expected = int(
        datetime.strptime(display, LOTTERY_TIME_DISPLAY_FMT)
        .replace(tzinfo=BEIJING_TZ)
        .timestamp()
    )
    assert unix == expected
    assert conditions["lottery_time_text"] == display
    assert "lottery_time_inferred" not in conditions


def test_lottery_time_from_llm_parse_rejects_chinese_text() -> None:
    unix, conditions = _lottery_time_from_llm_parse({"lottery_time": "2026年7月8日"})
    assert conditions.get("lottery_time_inferred") is True
    assert unix > 1_000_000_000


def test_lottery_time_from_llm_parse_default_when_null() -> None:
    unix, conditions = _lottery_time_from_llm_parse({"lottery_time": None})
    assert conditions.get("lottery_time_inferred") is True
    assert "lottery_time_text" in conditions
    assert abs(unix - (int(__import__("time").time()) + SIX_MONTHS_SECONDS)) < 5
