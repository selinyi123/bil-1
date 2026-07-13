from __future__ import annotations

import re

from src.lottery_time import (
    LOTTERY_TIME_DISPLAY_FMT,
    format_timestamp,
    is_relative_lottery_time_text,
    lottery_time_text,
    normalize_lottery_time_text,
)


def test_format_timestamp() -> None:
    text = format_timestamp(1784034000)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", text)


def test_normalize_month_day_hao() -> None:
    assert normalize_lottery_time_text("7月15号") == "2026-07-15 00:00"
    assert normalize_lottery_time_text("7月15号开奖") == "2026-07-15 00:00"


def test_normalize_relative_returns_empty() -> None:
    assert normalize_lottery_time_text("下周") == ""
    assert normalize_lottery_time_text("下周四") == ""
    assert normalize_lottery_time_text("下周五晚8点") == ""


def test_lottery_time_text_only_returns_standard_format() -> None:
    item = {"conditions": {"lottery_time_text": "下周"}}
    assert lottery_time_text(item) == ""

    item2 = {"conditions": {"lottery_time_text": "7月15号"}}
    assert lottery_time_text(item2) == "2026-07-15 00:00"

    item3 = {"lottery_time": 1784034000}
    text = lottery_time_text(item3)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", text)


def test_is_relative_lottery_time_text() -> None:
    assert is_relative_lottery_time_text("下周") is True
    assert is_relative_lottery_time_text("2026-07-15 11:00") is False
