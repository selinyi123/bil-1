from __future__ import annotations

import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web.auto_config import ALLOWED_CLICK_ACTIONS
from web.auto_scheduler import AutoScheduler, CollisionError, _is_hard_failure, _next_slot, _probe_job
from web.job_runner import JobRunner, JobStatus


@contextmanager
def _logged_in(*, llm: bool = False):
    """模拟已登录（可选 LLM 就绪）以通过 /api/jobs 前置政策。"""
    with patch("web.auto_scheduler.get_account_profile", return_value={"logged_in": True}), patch(
        "web.auto_scheduler.resolve_effective_uid", return_value=999001
    ):
        if llm:
            with patch("web.api_errors.is_llm_ready", return_value=True):
                yield
        else:
            yield


def _bind_resolve(runner: MagicMock, status_factory) -> None:
    """让 resolve_job_status 与 get_status 行为一致，供调度等待循环使用。"""

    def resolve(_job_id: int) -> JobStatus:
        value = status_factory()
        return value if isinstance(value, JobStatus) else JobStatus(**value)

    runner.resolve_job_status.side_effect = resolve


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
    runner.try_start.assert_not_called()
    runner.cancel.assert_not_called()


def test_collision_when_try_start_returns_none() -> None:
    runner = MagicMock()
    runner.is_running.return_value = False
    runner.try_start.return_value = None
    scheduler = AutoScheduler(job_runner=runner)
    with _logged_in(llm=True):
        with pytest.raises(CollisionError, match="已有任务正在运行"):
            scheduler._click_and_wait("refresh_all")
    runner.cancel.assert_not_called()


def test_wait_until_terminal_never_calls_cancel() -> None:
    runner = MagicMock()
    runner.is_running.return_value = False
    runner.try_start.return_value = 42
    poll_count = {"n": 0}

    def status_factory() -> JobStatus:
        poll_count["n"] += 1
        if poll_count["n"] < 2:
            return JobStatus(id=42, state="running", action="refresh_status", message="working")
        return JobStatus(id=42, state="success", action="refresh_status", message="done")

    _bind_resolve(runner, status_factory)
    scheduler = AutoScheduler(job_runner=runner)
    with _logged_in():
        scheduler._click_and_wait("refresh_status")
    runner.cancel.assert_not_called()
    runner.try_start.assert_called_once_with(
        "refresh_status", {}, source="auto", account_uid="999001"
    )


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
        "id": None,
        "state": "idle",
        "action": "",
        "message": "",
        "label": "",
    }
    runner.get_status.return_value = status
    result = _probe_job(runner)
    assert result["reachable"] is True
    assert result["job_state"] == "idle"
    assert result["job_id"] is None
    runner.get_status.assert_called()
    runner.try_start.assert_not_called()
    runner.cancel.assert_not_called()


def test_soft_failure_for_empty_triple() -> None:
    assert _is_hard_failure(RuntimeError("当前列表没有可参与的未参加活动")) is False
    assert _is_hard_failure(RuntimeError("当前没有可参与的未参加活动，已跳过")) is False
    assert _is_hard_failure(CollisionError("撞车")) is True
    assert _is_hard_failure(RuntimeError("请先扫码登录")) is True


def test_click_and_wait_treats_skipped_triple_as_success() -> None:
    runner = MagicMock()
    runner.is_running.return_value = False
    runner.try_start.return_value = 7
    _bind_resolve(
        runner,
        lambda: JobStatus(
            id=7,
            state="success",
            action="participate_triple",
            message="当前没有可参与的未参加活动，已跳过",
            result={"skipped": True, "items": []},
        ),
    )
    scheduler = AutoScheduler(job_runner=runner)
    with _logged_in(llm=True):
        outcome = scheduler._click_and_wait("participate_triple")
    assert outcome["skipped"] is True
    runner.try_start.assert_called_once_with(
        "participate_triple", {"from_auto": True}, source="auto", account_uid="999001"
    )
    runner.cancel.assert_not_called()


def test_click_and_wait_treats_legacy_empty_triple_error_as_skip() -> None:
    runner = MagicMock()
    runner.is_running.return_value = False
    runner.try_start.return_value = 8
    _bind_resolve(
        runner,
        lambda: JobStatus(
            id=8,
            state="error",
            action="participate_triple",
            message="当前列表没有可参与的未参加活动",
            result=None,
        ),
    )
    scheduler = AutoScheduler(job_runner=runner)
    with _logged_in(llm=True):
        outcome = scheduler._click_and_wait("participate_triple")
    assert outcome["skipped"] is True
    runner.cancel.assert_not_called()


def test_click_and_wait_cancelled_raises(isolated_home: Path) -> None:
    _ = isolated_home
    runner = MagicMock()
    runner.is_running.return_value = False
    runner.try_start.return_value = 9
    _bind_resolve(
        runner,
        lambda: JobStatus(
            id=9,
            state="cancelled",
            action="refresh_status",
            message="任务已取消",
        ),
    )
    scheduler = AutoScheduler(job_runner=runner)
    with _logged_in():
        with pytest.raises(RuntimeError, match="已取消"):
            scheduler._click_and_wait("refresh_status")
    runner.cancel.assert_not_called()


def test_click_and_wait_interrupted_raises(isolated_home: Path) -> None:
    _ = isolated_home
    runner = MagicMock()
    runner.is_running.return_value = False
    runner.try_start.return_value = 10
    _bind_resolve(
        runner,
        lambda: JobStatus(
            id=10,
            state="interrupted",
            action="refresh_status",
            message="进程退出，任务中断",
        ),
    )
    scheduler = AutoScheduler(job_runner=runner)
    with _logged_in():
        with pytest.raises(RuntimeError, match="中断"):
            scheduler._click_and_wait("refresh_status")
    runner.cancel.assert_not_called()


def test_next_slot_before_refresh() -> None:
    now = datetime(2026, 7, 17, 2, 56, tzinfo=timezone(timedelta(hours=8)))
    slot = _next_slot(now)
    assert slot["kind"] == "refresh"
    assert slot["hour"] == 3
    assert slot["action"] == "refresh_all"
    assert slot["action_label"] == "一键更新活动链接"
    assert slot["at_unix"]


def test_next_slot_triple_minute() -> None:
    now = datetime(2026, 7, 17, 2, 50, tzinfo=timezone(timedelta(hours=8)))
    slot = _next_slot(now)
    assert slot["kind"] == "triple"
    assert slot["minute"] == 55
    assert slot["action"] == "participate_triple"
    assert slot["action_label"] == "三连参与"


# ---------- P2 #18：AutoScheduler 统一前置政策（未登录 / LLM 未就绪 → soft 跳过） ----------


def test_auto_skips_refresh_when_not_logged_in() -> None:
    """未登录时调度触发 refresh_all → 跳过本次调度并记日志，不崩溃、不 try_start。"""
    runner = MagicMock()
    runner.is_running.return_value = False
    scheduler = AutoScheduler(job_runner=runner)
    with patch("web.auto_scheduler.get_account_profile", return_value={"logged_in": False}):
        outcome = scheduler._click_and_wait("refresh_all")
    assert outcome["skipped"] is True
    assert "登录" in outcome["message"]
    runner.try_start.assert_not_called()
    runner.cancel.assert_not_called()


def test_auto_skips_when_llm_not_ready() -> None:
    """已登录但 LLM 未就绪时 participate_triple 同样跳过，不崩溃。"""
    runner = MagicMock()
    runner.is_running.return_value = False
    scheduler = AutoScheduler(job_runner=runner)
    with patch("web.auto_scheduler.get_account_profile", return_value={"logged_in": True}):
        with patch("web.api_errors.is_llm_ready", return_value=False):
            outcome = scheduler._click_and_wait("participate_triple")
    assert outcome["skipped"] is True
    runner.try_start.assert_not_called()


# ---------- P2 #19：_is_hard_failure 优先按 error_kind 分类 ----------


def test_hard_failure_by_error_kind() -> None:
    """error_kind 结构化判定：business_partial/cancelled 为 soft，internal/business/network 为 hard。"""
    soft = RuntimeError("三连部分失败")
    soft.error_kind = "business_partial"
    assert _is_hard_failure(soft) is False
    cancelled = RuntimeError("任务已取消")
    cancelled.error_kind = "cancelled"
    assert _is_hard_failure(cancelled) is False
    network = RuntimeError("网络异常")
    network.error_kind = "network"
    assert _is_hard_failure(network) is True
    internal = RuntimeError("内部异常")
    internal.error_kind = "internal"
    assert _is_hard_failure(internal) is True
    business = RuntimeError("全部数据源检查失败")
    business.error_kind = "business"
    assert _is_hard_failure(business) is True
    # 无 error_kind：字符串兜底行为保留
    assert _is_hard_failure(RuntimeError("当前列表没有可参与的未参加活动")) is False
    assert _is_hard_failure(RuntimeError("连接超时")) is True


def test_identity_failure_is_hard() -> None:
    identity = RuntimeError("任务账号身份已变化")
    identity.error_kind = "identity"
    assert _is_hard_failure(identity) is True


def test_click_and_wait_error_attaches_error_kind() -> None:
    """job 终态 error 时 _click_and_wait 抛出的异常携带 error_kind（DB 行兜底）。"""
    runner = MagicMock()
    runner.is_running.return_value = False
    runner.try_start.return_value = 11
    _bind_resolve(
        runner,
        lambda: JobStatus(
            id=11,
            state="error",
            action="refresh_status",
            message="部分活动失败",
            result=None,
        ),
    )
    scheduler = AutoScheduler(job_runner=runner)
    with _logged_in():
        with patch("web.auto_scheduler.get_job", return_value={"error_kind": "business_partial"}):
            with pytest.raises(RuntimeError, match="部分活动失败") as exc_info:
                scheduler._click_and_wait("refresh_status")
    assert getattr(exc_info.value, "error_kind", None) == "business_partial"


def test_triple_slot_partial_failure_is_soft() -> None:
    """business_partial 在三连槽位按 soft 处理（记日志跳过），不致命停机。"""
    runner = MagicMock()
    runner.is_running.return_value = False
    runner.try_start.return_value = 12
    _bind_resolve(
        runner,
        lambda: JobStatus(
            id=12,
            state="error",
            action="participate_triple",
            message="部分活动参与失败",
            result=None,
        ),
    )
    scheduler = AutoScheduler(job_runner=runner)
    with _logged_in(llm=True):
        with patch("web.auto_scheduler.get_job", return_value={"error_kind": "business_partial"}):
            scheduler._run_triple_slot("2026-07-17-03-55")
    assert scheduler.get_status()["state"] != "fatal"
    assert "2026-07-17-03-55" in scheduler._done_triple
