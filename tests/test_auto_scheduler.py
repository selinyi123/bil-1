from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web.auto_config import ALLOWED_CLICK_ACTIONS
from web.auto_scheduler import AutoScheduler, CollisionError, _is_hard_failure, _next_slot, _probe_job
from web.job_runner import JobRunner


def test_allowed_actions_are_exactly_four() -> None:
    assert ALLOWED_CLICK_ACTIONS == frozenset(
        {
            "refresh_all",
            "refresh_watch",
            "refresh_status",
            "participate_triple",
        }
    )


def test_click_rejects_forbidden_action() -> None:
    scheduler = AutoScheduler(job_runner=JobRunner())
    with pytest.raises(ValueError, match="禁止的操作"):
        scheduler._click_and_wait("cancel")


def test_collision_when_runner_already_running() -> None:
    runner = MagicMock()
    runner.is_running.return_value = True
    runner.get_status.return_value.to_dict.return_value = {
        "state": "running",
        "action": "participate_triple",
        "message": "进行中",
    }
    scheduler = AutoScheduler(job_runner=runner)
    with pytest.raises(CollisionError, match="仍有任务在运行"):
        scheduler._click_and_wait("refresh_status")
    runner.start.assert_not_called()
    runner.cancel.assert_not_called()


def test_collision_when_start_returns_false() -> None:
    runner = MagicMock()
    runner.is_running.return_value = False
    runner.start.return_value = False
    scheduler = AutoScheduler(job_runner=runner)
    with pytest.raises(CollisionError, match="已有任务正在运行"):
        scheduler._click_and_wait("refresh_all")
    runner.cancel.assert_not_called()


def test_wait_until_idle_never_calls_cancel() -> None:
    runner = MagicMock()
    runner.is_running.return_value = False
    runner.start.return_value = True

    poll_count = {"n": 0}

    def get_status() -> MagicMock:
        poll_count["n"] += 1
        status = MagicMock()
        if poll_count["n"] < 2:
            status.to_dict.return_value = {"state": "running", "message": "working"}
        else:
            status.to_dict.return_value = {"state": "success", "message": "done"}
        return status

    runner.get_status.side_effect = get_status
    scheduler = AutoScheduler(job_runner=runner)
    scheduler._click_and_wait("refresh_status")
    runner.cancel.assert_not_called()


def test_collision_in_refresh_batch_propagates() -> None:
    runner = MagicMock()
    runner.is_running.return_value = True
    runner.get_status.return_value.to_dict.return_value = {
        "state": "running",
        "action": "refresh_all",
        "message": "busy",
    }
    scheduler = AutoScheduler(job_runner=runner)
    with pytest.raises(CollisionError):
        scheduler._run_refresh_batch("2026-07-17-3")
    runner.cancel.assert_not_called()


def test_probe_only_reads_runner_status() -> None:
    runner = MagicMock()
    status = MagicMock()
    status.to_dict.return_value = {
        "state": "idle",
        "action": "",
        "message": "",
        "label": "",
    }
    runner.get_status.return_value = status
    result = _probe_job(runner)
    assert result["reachable"] is True
    assert result["job_state"] == "idle"
    runner.get_status.assert_called()
    runner.start.assert_not_called()
    runner.cancel.assert_not_called()


def test_soft_failure_for_empty_triple() -> None:
    assert _is_hard_failure(RuntimeError("当前列表没有可参与的未参加活动")) is False
    assert _is_hard_failure(CollisionError("撞车")) is True
    assert _is_hard_failure(RuntimeError("请先扫码登录")) is True


def test_next_slot_before_refresh() -> None:
    now = datetime(2026, 7, 17, 2, 56, tzinfo=ZoneInfo("Asia/Shanghai"))
    slot = _next_slot(now)
    assert slot["kind"] == "refresh"
    assert slot["hour"] == 3
    assert slot["action"] == "refresh_all"
    assert slot["action_label"] == "一键更新活动链接"
    assert slot["at_unix"]


def test_next_slot_triple_minute() -> None:
    now = datetime(2026, 7, 17, 2, 50, tzinfo=ZoneInfo("Asia/Shanghai"))
    slot = _next_slot(now)
    assert slot["kind"] == "triple"
    assert slot["minute"] == 55
    assert slot["action"] == "participate_triple"
    assert slot["action_label"] == "三连参与"
