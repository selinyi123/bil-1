from __future__ import annotations

import time

from src.draw_reminder import (
    DRAWING_SOON_SECONDS,
    classify_participated_draw,
    compute_draw_reminders,
    matches_draw_window_filter,
)
from src.participation_store import ParticipationRecord


def _participation(dynamic_id: str) -> ParticipationRecord:
    return ParticipationRecord(
        dynamic_id=dynamic_id,
        user_status="已参加",
        updated_at=int(time.time()),
    )


def test_classify_past_participated_activity_not_drawn() -> None:
    now = 1_700_000_000
    item = {
        "dynamic_id": "123",
        "lottery_time": now - 3600,
        "prizes": [{"description": "键盘"}],
    }
    participation = _participation("123")
    assert classify_participated_draw(item, participation, now=now) is None


def test_classify_drawing_soon_activity() -> None:
    now = 1_700_000_000
    item = {
        "dynamic_id": "456",
        "lottery_time": now + 24 * 3600,
        "prizes": [{"description": "鼠标"}],
    }
    participation = _participation("456")
    assert classify_participated_draw(item, participation, now=now) == "soon"


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
    assert reminder["drawing_soon_count"] == 1
    assert "drawn_participated_count" not in reminder
    assert reminder["drawing_soon"][0]["dynamic_id"] == "2"


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


def test_matches_draw_window_filter_ignores_drawn() -> None:
    now = 1_700_000_000
    item = {
        "dynamic_id": "123",
        "lottery_time": now - 3600,
        "prizes": [{"description": "键盘"}],
    }
    participation = _participation("123")
    assert matches_draw_window_filter(item, participation, "drawn", now=now) is True


def test_matches_draw_window_filter_uses_stored_draw_tag() -> None:
    item = {
        "dynamic_id": "stored",
        "status_classified": True,
        "draw_tag": "即将开奖",
        "activity_status": "已参加",
    }
    assert matches_draw_window_filter(item, None, "soon") is True
    assert matches_draw_window_filter(item, None, "drawn") is True


def test_list_activities_draw_window_ignores_status_filter() -> None:
    from web.activity_service import list_activities

    soon = list_activities(draw_window="soon")
    if not soon["total"]:
        return
    with_status = list_activities(draw_window="soon", status="已参加")
    assert with_status["total"] == soon["total"]
