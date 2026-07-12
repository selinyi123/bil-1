from __future__ import annotations

from typing import Literal

from src.lottery_classifier import LotteryType
from src.participation_store import ParticipationRecord

ActivityStatus = Literal["已结束", "已参加", "未参加"]
StatusSource = Literal["platform", "participate", "default"]
DrawStatus = Literal["active", "ended"]


def platform_joined(
    *,
    lottery_type: LotteryType,
    platform_participated: bool | None,
    reserve_reserved: bool | None,
    conditions: dict[str, int | bool] | None,
) -> bool:
    if lottery_type == "预约抽奖":
        if reserve_reserved:
            return True
        return bool(platform_participated)

    if lottery_type == "互动抽奖":
        return bool(platform_participated)

    return False


def resolve_activity_status(
    *,
    draw_status: DrawStatus,
    lottery_type: LotteryType,
    platform_participated: bool | None,
    reserve_reserved: bool | None,
    conditions: dict[str, int | bool] | None,
    participation: ParticipationRecord | None,
) -> tuple[ActivityStatus, StatusSource]:
    if draw_status == "ended":
        return "已结束", "platform"

    if participation is not None and participation.user_status == "已参加":
        return "已参加", "participate"

    if lottery_type == "转发抽奖":
        return "未参加", "default"

    joined = platform_joined(
        lottery_type=lottery_type,
        platform_participated=platform_participated,
        reserve_reserved=reserve_reserved,
        conditions=conditions,
    )
    return ("已参加" if joined else "未参加"), "platform"
