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


def test_normalize_spaced_chinese_date() -> None:
    assert normalize_lottery_time_text("2026 年 7 月 15 日晚") == "2026-07-15 20:00"
    assert normalize_lottery_time_text("7月15号当天") == "2026-07-15 00:00"


def test_normalize_next_weekday_with_ref() -> None:
    from datetime import datetime

    from src.lottery_time import BEIJING_TZ

    ref = datetime(2026, 7, 14, 12, 0, tzinfo=BEIJING_TZ)
    assert normalize_lottery_time_text("下周三", ref=ref) == "2026-07-22 00:00"


def test_migrate_stored_lottery_times() -> None:
    from src.lottery_time import migrate_stored_lottery_times

    activities = [
        {
            "dynamic_id": "1",
            "enriched_at": 1784119200,
            "conditions": {"lottery_time_text": "7月15号"},
        },
        {
            "dynamic_id": "2",
            "enriched_at": 1784119200,
            "conditions": {"lottery_time_text": "下周"},
        },
    ]
    migrated = migrate_stored_lottery_times(activities)
    assert migrated == 2
    assert activities[0]["lottery_time"]
    assert activities[0]["conditions"]["lottery_time_text"] == "2026-07-15 00:00"
    assert activities[1]["conditions"]["lottery_time_text"] == ""


def test_lottery_time_text_only_returns_standard_format() -> None:
    item = {"conditions": {"lottery_time_text": "下周"}}
    assert lottery_time_text(item) == ""

    item2 = {"conditions": {"lottery_time_text": "7月15号"}}
    assert lottery_time_text(item2) == "2026-07-15 00:00"

    item3 = {"lottery_time": 1784034000}
    text = lottery_time_text(item3)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", text)


def test_normalize_evening_hour() -> None:
    assert normalize_lottery_time_text("7月20日晚8点") == "2026-07-20 20:00"
    assert normalize_lottery_time_text("7月14日 18:00") == "2026-07-14 18:00"


def test_format_timestamp_beijing() -> None:
    text = format_timestamp(1784119200)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", text)


def test_is_standard_lottery_time_display() -> None:
    from src.lottery_time import is_standard_lottery_time_display

    assert is_standard_lottery_time_display("2026-07-14 18:00") is True
    assert is_standard_lottery_time_display("7月15号") is False
