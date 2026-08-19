from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import patch

from src.bilibili_login import LoginCancelledError
from src.job_store import get_job
from web.job_runner import JobRunner


def _wait_until(runner: JobRunner, predicate, timeout: float = 3.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate(runner.get_status()):
            return
        time.sleep(0.05)
    raise AssertionError(f"timeout waiting for job state: {runner.get_status().to_dict()}")


def test_final_log_replaces_progress_appends(isolated_home: Path) -> None:
    _ = isolated_home
    runner = JobRunner()
    done = threading.Event()

    def fake_run_action(action, params, *, on_progress, cancel_event):
        on_progress(step=1, total=2, message="检查中", log_append="【DS-1】同一专栏，已跳过")
        on_progress(step=2, total=2, message="完成", log_append="【跳过流水线】均无新专栏")
        done.set()
        return {
            "ok": True,
            "message": "检查完成",
            "log": "【DS-1】同一专栏，已跳过\n【跳过流水线】均无新专栏",
        }

    with patch("web.job_runner.run_action", side_effect=fake_run_action):
        job_id = runner.try_start("refresh_all")
        assert job_id is not None
        assert done.wait(timeout=3)

    _wait_until(runner, lambda s: s.state != "running")
    status = runner.get_status()
    assert status.state == "success"
    assert status.id == job_id
    assert status.log == "【DS-1】同一专栏，已跳过\n【跳过流水线】均无新专栏"
    assert status.log.count("【DS-1】") == 1
    row = get_job(job_id)
    assert row is not None
    assert row["state"] == "success"


def test_login_success_preserves_login_phase(isolated_home: Path) -> None:
    _ = isolated_home
    runner = JobRunner()
    done = threading.Event()

    def fake_run_action(action, params, *, on_progress, cancel_event):
        on_progress(step=1, total=1, message="扫码成功", login_phase="scanned")
        on_progress(step=1, total=1, message="登录成功", login_phase="confirming")
        done.set()
        return {
            "ok": True,
            "message": "登录成功，账号已就绪",
            "log": "ok",
            "result": {"login_phase": "success"},
        }

    with patch("web.job_runner.run_action", side_effect=fake_run_action):
        assert runner.start("login") is True
        assert done.wait(timeout=3)

    _wait_until(runner, lambda s: s.state != "running")
    status = runner.get_status()
    assert status.state == "success"
    assert status.result is not None
    assert status.result.get("login_phase") == "success"


def test_login_error_sets_error_phase(isolated_home: Path) -> None:
    _ = isolated_home
    runner = JobRunner()
    done = threading.Event()

    def fake_run_action(action, params, *, on_progress, cancel_event):
        on_progress(step=1, total=1, message="等待扫码", login_phase="waiting")
        done.set()
        raise RuntimeError("boom")

    with patch("web.job_runner.run_action", side_effect=fake_run_action):
        assert runner.start("login") is True
        assert done.wait(timeout=3)

    _wait_until(runner, lambda s: s.state == "error")
    status = runner.get_status()
    assert status.state == "error"
    assert status.result is not None
    assert status.result.get("login_phase") == "error"


def test_login_cancel_becomes_cancelled(isolated_home: Path) -> None:
    _ = isolated_home
    runner = JobRunner()
    done = threading.Event()

    def fake_run_action(action, params, *, on_progress, cancel_event):
        done.set()
        raise LoginCancelledError("用户取消")

    with patch("web.job_runner.run_action", side_effect=fake_run_action):
        job_id = runner.try_start("login")
        assert job_id is not None
        assert done.wait(timeout=3)

    _wait_until(runner, lambda s: s.state == "cancelled")
    status = runner.get_status()
    assert status.state == "cancelled"
    row = get_job(job_id)
    assert row is not None
    assert row["state"] == "cancelled"


def test_triple_cancel_exception_becomes_cancelled(isolated_home: Path) -> None:
    _ = isolated_home
    runner = JobRunner()
    started = threading.Event()

    def fake_run_action(action, params, *, on_progress, cancel_event):
        started.set()
        while cancel_event is not None and not cancel_event.is_set():
            time.sleep(0.02)
        raise ValueError("任务已取消")

    with patch("web.job_runner.run_action", side_effect=fake_run_action):
        job_id = runner.try_start("participate_triple")
        assert job_id is not None
        assert started.wait(timeout=3)
        assert runner.cancel() is True
        _wait_until(runner, lambda s: s.state == "cancelled")

    assert get_job(job_id)["state"] == "cancelled"


def test_triple_internal_failure_becomes_error_with_partial_results(isolated_home: Path) -> None:
    """核心不变量：三连内部失败终态为 error（非 cancelled），
    且已完成的 activity 摘要随 result.partial_failure 保留（partial_failure 语义）。"""
    from web.actions import TripleParticipateFailed

    _ = isolated_home
    runner = JobRunner()
    done = threading.Event()

    def fake_run_action(action, params, *, on_progress, cancel_event):
        done.set()
        raise TripleParticipateFailed(
            "三连参与失败（602）：评论 API 报错",
            completed=[
                {
                    "dynamic_id": "601",
                    "activity_title": "活动A",
                    "lottery_type": "互动抽奖",
                    "actions": [{"action": "like", "ok": True}, {"action": "repost", "ok": True}],
                }
            ],
            failed_dynamic_id="602",
        )

    with patch("web.job_runner.run_action", side_effect=fake_run_action):
        job_id = runner.try_start("participate_triple")
        assert job_id is not None
        assert done.wait(timeout=3)

    _wait_until(runner, lambda s: s.state == "error")
    status = runner.get_status()
    assert status.state == "error"
    assert status.result is not None
    assert status.result.get("partial_failure") is True
    assert status.result.get("failed_dynamic_id") == "602"
    completed = status.result.get("completed") or []
    assert len(completed) == 1
    assert completed[0]["dynamic_id"] == "601"
    assert {"action": "repost", "ok": True} in completed[0]["actions"]
    row = get_job(job_id)
    assert row is not None
    assert row["state"] == "error"
    # 业务部分失败应有独立 error_kind，不得污染"内部程序异常"统计
    assert row["error_kind"] == "business_partial"


def test_a1_rejects_second_start(isolated_home: Path) -> None:
    _ = isolated_home
    runner = JobRunner()
    gate = threading.Event()
    started = threading.Event()

    def fake_run_action(action, params, *, on_progress, cancel_event):
        started.set()
        gate.wait(timeout=3)
        return {"ok": True, "message": "ok", "log": "ok"}

    with patch("web.job_runner.run_action", side_effect=fake_run_action):
        first = runner.try_start("refresh_status")
        assert first is not None
        assert started.wait(timeout=3)
        assert runner.try_start("refresh_all") is None
        assert runner.start("refresh_all") is False
        gate.set()
        _wait_until(runner, lambda s: s.state == "success")


def test_bound_account_uid_roundtrips_and_allows_matching_identity(isolated_home: Path) -> None:
    _ = isolated_home
    runner = JobRunner()
    done = threading.Event()

    def fake_run_action(action, params, *, on_progress, cancel_event):
        done.set()
        return {"ok": True, "message": "ok", "log": "ok"}

    with patch("web.job_runner.resolve_effective_uid", return_value=123456), patch(
        "web.job_runner.run_action", side_effect=fake_run_action
    ):
        job_id = runner.try_start("refresh_status", account_uid=123456)
        assert job_id is not None
        assert done.wait(timeout=3)
        _wait_until(runner, lambda s: s.state == "success")

    status = runner.get_status()
    assert status.account_uid == "123456"
    assert status.to_dict()["account_uid"] == "123456"
    row = get_job(job_id)
    assert row is not None
    assert row["account_uid"] == "123456"


def test_bound_account_uid_mismatch_fails_before_run_action(isolated_home: Path) -> None:
    _ = isolated_home
    runner = JobRunner()
    action_called = threading.Event()

    def fake_run_action(action, params, *, on_progress, cancel_event):
        action_called.set()
        return {"ok": True, "message": "must not run"}

    with patch("web.job_runner.resolve_effective_uid", return_value=654321), patch(
        "web.job_runner.run_action", side_effect=fake_run_action
    ) as action_mock:
        job_id = runner.try_start("refresh_status", account_uid="123456")
        assert job_id is not None
        _wait_until(runner, lambda s: s.state == "error")
        action_mock.assert_not_called()

    assert not action_called.is_set()
    row = get_job(job_id)
    assert row is not None
    assert row["state"] == "error"
    assert row["error_kind"] == "identity"
    assert row["account_uid"] == "123456"


def test_bound_participate_passes_one_captured_context_to_run_action(
    isolated_home: Path,
) -> None:
    _ = isolated_home
    runner = JobRunner()
    done = threading.Event()
    captured = object()
    received: dict[str, object] = {}

    def fake_run_action(action, params, *, on_progress, cancel_event, account_context):
        received["action"] = action
        received["context"] = account_context
        done.set()
        return {"ok": True, "message": "ok", "log": "ok"}

    with (
        patch("web.job_runner.resolve_effective_uid", return_value=123456),
        patch("web.job_runner.capture_current_account_context", return_value=captured) as capture,
        patch("web.job_runner.run_action", side_effect=fake_run_action),
    ):
        job_id = runner.try_start("participate", account_uid=123456)
        assert job_id is not None
        assert done.wait(timeout=3)
        _wait_until(runner, lambda s: s.state == "success")

    capture.assert_called_once_with(expected_uid="123456")
    assert received == {"action": "participate", "context": captured}


def test_recover_marks_running_interrupted(isolated_home: Path) -> None:
    _ = isolated_home
    from src.job_store import insert_running_job

    job_id = insert_running_job(action="refresh_all", label="一键更新", source="ui", params={})
    runner = JobRunner()
    runner.recover_on_startup()
    row = get_job(job_id)
    assert row is not None
    assert row["state"] == "interrupted"
    status = runner.get_status()
    assert status.id == job_id
    assert status.state == "interrupted"


def test_resolve_missing_job_not_confused_with_current(isolated_home: Path) -> None:
    _ = isolated_home
    runner = JobRunner()
    done = threading.Event()

    def fake_run_action(action, params, *, on_progress, cancel_event):
        done.set()
        return {"ok": True, "message": "ok", "log": "ok"}

    with patch("web.job_runner.run_action", side_effect=fake_run_action):
        job_id = runner.try_start("refresh_status")
        assert job_id is not None
        assert done.wait(timeout=3)
    _wait_until(runner, lambda s: s.state == "success")

    missing = runner.resolve_job_status(job_id + 999)
    assert missing.id == job_id + 999
    assert missing.state == "interrupted"
    assert runner.get_status().state == "success"
