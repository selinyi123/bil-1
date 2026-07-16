from __future__ import annotations

from src.fetch_activity_info import is_enriched_complete, list_missing_enrich_tasks


def test_is_enriched_complete() -> None:
    assert not is_enriched_complete(None)
    assert is_enriched_complete({"skipped": True, "lottery_type": "充电抽奖"})
    assert not is_enriched_complete({"skipped": True, "lottery_type": "转发抽奖"})
    assert is_enriched_complete(
        {
            "lottery_time": 1,
            "prizes": [{"tier": "first", "winner_count": 1, "description": "x"}],
            "repost_fetched": True,
        }
    )


def test_list_missing_enrich_tasks(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.fetch_activity_info._load_existing_activities",
        lambda: {
            "1000000000000000001": {
                "dynamic_id": "1000000000000000001",
                "lottery_type": "互动抽奖",
            },
            "2000000000000000002": {
                "dynamic_id": "2000000000000000002",
                "lottery_type": "充电抽奖",
            },
            "3000000000000000003": {
                "dynamic_id": "3000000000000000003",
                "lottery_type": "转发抽奖",
                "lottery_time": 1,
                "prizes": [{"tier": "first", "winner_count": 1, "description": "x"}],
                "repost_fetched": True,
            },
        },
    )
    monkeypatch.setattr(
        "src.fetch_activity_info.is_enriched_complete",
        lambda cached: str(cached.get("dynamic_id")) == "3000000000000000003",
    )
    tasks = list_missing_enrich_tasks()
    assert tasks == [("1000000000000000001", "互动抽奖")]
