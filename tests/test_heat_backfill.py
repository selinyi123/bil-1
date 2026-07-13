from __future__ import annotations

from src.fetch_activity_info import _cache_missing_repost_count, count_pending_heat_backfill


def test_cache_missing_repost_when_never_fetched() -> None:
    assert _cache_missing_repost_count({"repost_count": 0}) is True


def test_cache_missing_repost_when_zero_not_confirmed() -> None:
    cached = {"repost_count": 0, "repost_fetched": True, "repost_zero_confirmed": False}
    assert _cache_missing_repost_count(cached) is True


def test_cache_complete_when_zero_confirmed() -> None:
    cached = {"repost_count": 0, "repost_fetched": True, "repost_zero_confirmed": True}
    assert _cache_missing_repost_count(cached) is False


def test_count_pending_heat_backfill_skips_charging(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.fetch_activity_info._load_existing_activities",
        lambda: {
            "1": {"lottery_type": "互动抽奖", "repost_count": 0},
            "2": {"lottery_type": "充电抽奖", "repost_count": 0},
        },
    )
    assert count_pending_heat_backfill() == 1


def test_count_pending_heat_backfill_includes_reserve_lottery_without_flag(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.fetch_activity_info._load_existing_activities",
        lambda: {
            "1": {
                "lottery_type": "预约抽奖",
                "repost_count": 0,
                "repost_fetched": True,
                "repost_zero_confirmed": True,
                "heat_from_reserve": False,
            },
        },
    )
    assert count_pending_heat_backfill() == 1
