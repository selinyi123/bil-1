from __future__ import annotations

from src.participation import _is_notice_active


def test_notice_active_when_open() -> None:
    ok, reason = _is_notice_active({"status": 0, "lottery_time": 0})
    assert ok is True
    assert reason == ""


def test_notice_inactive_when_missing() -> None:
    ok, reason = _is_notice_active(None)
    assert ok is False
    assert "未找到" in reason


def test_notice_inactive_when_ended() -> None:
    ok, reason = _is_notice_active({"status": 1, "lottery_time": 0})
    assert ok is False
    assert "结束" in reason
