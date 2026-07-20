from __future__ import annotations

from pathlib import Path

import pytest

from src.db.models import MessageWatchRow
from src.db.session import session_scope
from src.message_watch import (
    acknowledge_at_unread,
    evaluate_at_unread_alert,
    get_last_seen_at_unread,
)


@pytest.fixture
def uid(isolated_home: Path) -> int:
    _ = isolated_home
    return 424242


def test_first_check_establishes_baseline_without_alert(uid: int) -> None:
    alert = evaluate_at_unread_alert(uid, 3)
    assert alert.increased is False
    assert alert.current == 3
    assert get_last_seen_at_unread(uid) == 3


def test_increase_triggers_alert(uid: int) -> None:
    evaluate_at_unread_alert(uid, 2)
    alert = evaluate_at_unread_alert(uid, 5)
    assert alert.increased is True
    assert alert.delta == 3
    assert alert.previous == 2
    assert alert.current == 5
    assert get_last_seen_at_unread(uid) == 2


def test_decrease_updates_baseline_silently(uid: int) -> None:
    evaluate_at_unread_alert(uid, 4)
    alert = evaluate_at_unread_alert(uid, 1)
    assert alert.increased is False
    assert get_last_seen_at_unread(uid) == 1


def test_acknowledge_clears_pending_alert(uid: int) -> None:
    evaluate_at_unread_alert(uid, 1)
    evaluate_at_unread_alert(uid, 4)
    acknowledge_at_unread(uid, 4)
    alert = evaluate_at_unread_alert(uid, 4)
    assert alert.increased is False
    assert get_last_seen_at_unread(uid) == 4


def test_message_watch_persists(uid: int) -> None:
    evaluate_at_unread_alert(uid, 7)
    with session_scope() as session:
        row = session.get(MessageWatchRow, uid)
        assert row is not None
        assert row.last_seen_unread_at == 7
