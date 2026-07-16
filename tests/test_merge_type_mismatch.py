from __future__ import annotations

from src.fetch_activity_info import _restore_existing_activity


def test_restore_existing_activity_falls_back_to_cached_type() -> None:
    cached = {
        "dynamic_id": "1221021101641957383",
        "source_url": "https://www.bilibili.com/opus/1221021101641957383",
        "lottery_type": "转发抽奖",
        "enriched_at": 1,
        "business_id": "1221021101641957383",
        "business_type": 0,
        "draw_status": "active",
        "lottery_time": None,
        "prizes": [{"tier": "first", "winner_count": 1, "description": "奖品"}],
        "participants": 0,
        "repost_count": 10,
        "repost_fetched": True,
        "conditions": {},
        "skipped": False,
        "activity_status": "未参加",
        "user_status_source": "default",
    }
    restored = _restore_existing_activity(
        dynamic_id="1221021101641957383",
        lottery_type="互动抽奖",
        cached=cached,
        participation=None,
    )
    assert restored is not None
    assert restored.lottery_type == "转发抽奖"
