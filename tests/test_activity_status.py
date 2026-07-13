from __future__ import annotations

from src.activity_status import platform_joined, resolve_activity_status
from src.participation_store import ParticipationRecord


def test_ended_draw_status() -> None:
    status, source = resolve_activity_status(
        draw_status="ended",
        lottery_type="互动抽奖",
        platform_participated=False,
        reserve_reserved=None,
        conditions={},
        participation=None,
    )
    assert status == "已结束"
    assert source == "platform"


def test_participation_overrides_platform() -> None:
    participation = ParticipationRecord(
        dynamic_id="1220298825599549447",
        user_status="已参加",
        updated_at=1,
    )
    status, source = resolve_activity_status(
        draw_status="active",
        lottery_type="互动抽奖",
        platform_participated=False,
        reserve_reserved=None,
        conditions={},
        participation=participation,
    )
    assert status == "已参加"
    assert source == "participate"


def test_forward_lottery_defaults_unjoined() -> None:
    status, source = resolve_activity_status(
        draw_status="active",
        lottery_type="转发抽奖",
        platform_participated=True,
        reserve_reserved=None,
        conditions={},
        participation=None,
    )
    assert status == "未参加"
    assert source == "default"


def test_reserve_joined_from_button() -> None:
    assert platform_joined(
        lottery_type="预约抽奖",
        platform_participated=False,
        reserve_reserved=True,
        conditions={},
    )
