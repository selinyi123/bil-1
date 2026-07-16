from __future__ import annotations

from src.fetch_activity_info import count_pending_enrich, list_missing_enrich_tasks


def test_list_missing_enrich_tasks_excludes_charging_and_complete(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.fetch_activity_info._load_existing_activities",
        lambda: {
            "1000000000000000001": {
                "dynamic_id": "1000000000000000001",
                "lottery_type": "互动抽奖",
            },
            "2000000000000000002": {
                "dynamic_id": "2000000000000000002",
                "lottery_type": "转发抽奖",
            },
            "3000000000000000003": {
                "dynamic_id": "3000000000000000003",
                "lottery_type": "充电抽奖",
            },
            "4000000000000000004": {
                "dynamic_id": "4000000000000000004",
                "lottery_type": "预约抽奖",
                "lottery_time": 1,
                "prizes": ["x"],
                "repost_fetched": True,
            },
        },
    )
    monkeypatch.setattr(
        "src.fetch_activity_info.is_enriched_complete",
        lambda cached: cached.get("dynamic_id") == "4000000000000000004",
    )
    tasks = list_missing_enrich_tasks()
    assert tasks == [
        ("1000000000000000001", "互动抽奖"),
        ("2000000000000000002", "转发抽奖"),
    ]


def test_count_pending_enrich(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.fetch_activity_info._load_existing_activities",
        lambda: {
            "1000000000000000001": {
                "dynamic_id": "1000000000000000001",
                "lottery_type": "互动抽奖",
            }
        },
    )
    monkeypatch.setattr("src.fetch_activity_info.is_enriched_complete", lambda _cached: False)
    assert count_pending_enrich() == 1
