from __future__ import annotations

from src.lottery_enricher import EnrichedActivity, PrizeTier, _apply_default_lottery_time
from src.lottery_time import SIX_MONTHS_SECONDS, default_lottery_time_from_now


def test_default_lottery_time_from_now() -> None:
    now = 1_000_000
    assert default_lottery_time_from_now(now=now) == now + SIX_MONTHS_SECONDS


def test_apply_default_lottery_time_on_missing() -> None:
    activity = EnrichedActivity(
        dynamic_id="1000000000000000001",
        source_url="https://www.bilibili.com/opus/1000000000000000001",
        lottery_type="转发抽奖",
        enriched_at=1_000_000,
        business_id="1000000000000000001",
        business_type=0,
        draw_status="active",
        lottery_time=None,
        prizes=[PrizeTier(tier="first", winner_count=1, description="奖品")],
        participants=0,
        conditions={},
        winners=None,
        platform_participated=None,
        repost_fetched=True,
    )
    updated = _apply_default_lottery_time(activity)
    assert updated.lottery_time == default_lottery_time_from_now()
    assert updated.conditions.get("lottery_time_inferred") is True
    assert updated.conditions.get("lottery_time_text")
