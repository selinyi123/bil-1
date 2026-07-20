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
