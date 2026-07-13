from __future__ import annotations

import time

from src.draw_reminder import (
    DRAWING_SOON_SECONDS,
    classify_participated_draw,
    compute_draw_reminders,
    matches_draw_window_filter,
    should_recommend_at_check,
)
from src.participation_store import ParticipationRecord


def _participation(dynamic_id: str) -> ParticipationRecord:
    return ParticipationRecord(
        dynamic_id=dynamic_id,
        user_status="已参加",
        updated_at=int(time.time()),
    )


def test_classify_drawn_participated_activity() -> None:
    now = 1_700_000_000
    item = {
        "dynamic_id": "123",
        "lottery_time": now - 3600,
        "prizes": [{"description": "键盘"}],
    }
    participation = _participation("123")
    assert classify_participated_draw(item, participation, now=now) == "drawn"
    assert should_recommend_at_check(item, participation, now=now) is True


def test_classify_drawing_soon_activity() -> None:
    now = 1_700_000_000
    item = {
        "dynamic_id": "456",
        "lottery_time": now + 24 * 3600,
        "prizes": [{"description": "鼠标"}],
    }
    participation = _participation("456")
    assert classify_participated_draw(item, participation, now=now) == "soon"
    assert should_recommend_at_check(item, participation, now=now) is False


def test_compute_draw_reminders_groups_counts() -> None:
    now = 1_700_000_000
    activities = [
        {
            "dynamic_id": "1",
            "lottery_time": now - 100,
            "prizes": [{"description": "奖品A"}],
        },
        {
            "dynamic_id": "2",
            "lottery_time": now + 3600,
            "prizes": [{"description": "奖品B"}],
        },
        {
            "dynamic_id": "3",
            "lottery_time": now + 5 * 24 * 3600,
            "prizes": [{"description": "奖品C"}],
        },
    ]
    participations = {
        "1": _participation("1"),
        "2": _participation("2"),
        "3": _participation("3"),
    }
    reminder = compute_draw_reminders(activities, participations, now=now)
    assert reminder["drawn_participated_count"] == 1
    assert reminder["drawing_soon_count"] == 1
    assert reminder["drawn_participated"][0]["dynamic_id"] == "1"
    assert reminder["drawing_soon"][0]["dynamic_id"] == "2"


def test_classify_drawn_only_within_three_day_window() -> None:
    now = 1_700_000_000
    item = {
        "dynamic_id": "old",
        "lottery_time": now - DRAWING_SOON_SECONDS - 1,
        "prizes": [{"description": "过期"}],
    }
    participation = _participation("old")
    assert classify_participated_draw(item, participation, now=now) == "pending"
    assert matches_draw_window_filter(item, participation, "drawn", now=now) is False


def test_classify_soon_only_within_three_day_window() -> None:
    now = 1_700_000_000
    item = {
        "dynamic_id": "far",
        "lottery_time": now + DRAWING_SOON_SECONDS + 1,
        "prizes": [{"description": "太远"}],
    }
    participation = _participation("far")
    assert classify_participated_draw(item, participation, now=now) == "pending"
    assert matches_draw_window_filter(item, participation, "soon", now=now) is False


def test_matches_draw_window_filter_respects_participation() -> None:
    now = 1_700_000_000
    item = {
        "dynamic_id": "123",
        "lottery_time": now - 3600,
        "prizes": [{"description": "键盘"}],
    }
    assert matches_draw_window_filter(item, None, "drawn", now=now) is False
    assert matches_draw_window_filter(item, _participation("123"), "drawn", now=now) is True


def test_list_activities_draw_window_ignores_status_filter() -> None:
    from web.activity_service import list_activities

    drawn = list_activities(draw_window="drawn")
    if not drawn["total"]:
        return
    with_status = list_activities(draw_window="drawn", status="已参加")
    assert with_status["total"] == drawn["total"]
