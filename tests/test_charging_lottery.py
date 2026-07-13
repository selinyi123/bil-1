from __future__ import annotations

from src.lottery_classifier import (
    UPOWER_BUSINESS_TYPE,
    is_charging_lottery_activity,
    migrate_charging_lottery_fields,
    migrate_stored_charging_lotteries,
)


def test_is_charging_lottery_activity_by_business_type() -> None:
    item = {"lottery_type": "互动抽奖", "business_type": UPOWER_BUSINESS_TYPE}
    assert is_charging_lottery_activity(item) is True


def test_migrate_charging_lottery_fields() -> None:
    item = {
        "dynamic_id": "1213708271262629897",
        "lottery_type": "互动抽奖",
        "business_type": UPOWER_BUSINESS_TYPE,
        "skipped": False,
        "skip_reason": None,
    }
    assert migrate_charging_lottery_fields(item) is True
    assert item["lottery_type"] == "充电抽奖"
    assert item["skipped"] is True
    assert item["skip_reason"] == "充电专属抽奖，不参与"
    assert migrate_charging_lottery_fields(item) is False


def test_migrate_stored_charging_lotteries_batch() -> None:
    activities = [
        {"lottery_type": "互动抽奖", "business_type": UPOWER_BUSINESS_TYPE},
        {"lottery_type": "转发抽奖", "business_type": 0},
        {"lottery_type": "充电抽奖", "skipped": True, "skip_reason": "充电专属抽奖，不参与"},
    ]
    assert migrate_stored_charging_lotteries(activities) == 1
