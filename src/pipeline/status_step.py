from __future__ import annotations

import time

from src.draw_reminder import DRAWING_SOON_SECONDS

THREE_DAYS = DRAWING_SOON_SECONDS


def apply_initial_status(activity: dict, *, now: int | None = None) -> dict:
    """为新入库活动计算参与状态与开奖标签（已结束仅由开奖时间决定）。"""
    current = int(now if now is not None else time.time())
    lottery_time = activity.get("lottery_time")
    try:
        deadline = int(lottery_time) if lottery_time else 0
    except (TypeError, ValueError):
        deadline = 0

    activity["activity_status"] = "未参加"
    activity["user_status_source"] = "default"
    activity["draw_tag"] = ""
    activity["status_classified"] = True

    if deadline <= 0:
        activity["draw_status"] = "active"
        return activity

    if current > deadline:
        activity["activity_status"] = "已结束"
        activity["draw_status"] = "ended"
        activity["draw_tag"] = ""
        return activity

    activity["draw_status"] = "active"
    if deadline - THREE_DAYS <= current < deadline:
        activity["draw_tag"] = "即将开奖"
    else:
        activity["draw_tag"] = ""
    return activity
