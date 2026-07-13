from __future__ import annotations

import threading
import time
from unittest.mock import patch

from web.job_runner import JobRunner


def test_login_success_preserves_login_phase() -> None:
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

    for _ in range(50):
        status = runner.get_status()
        if status.state != "running":
            break
        time.sleep(0.05)

    status = runner.get_status()
    assert status.state == "success"
    assert status.result is not None
    assert status.result.get("login_phase") == "success"


def test_login_error_sets_error_phase() -> None:
    runner = JobRunner()
    done = threading.Event()

    def fake_run_action(action, params, *, on_progress, cancel_event):
        on_progress(step=1, total=1, message="等待扫码", login_phase="waiting")
        done.set()
        raise RuntimeError("boom")

    with patch("web.job_runner.run_action", side_effect=fake_run_action):
        assert runner.start("login") is True
        assert done.wait(timeout=3)

    for _ in range(50):
        status = runner.get_status()
        if status.state == "error":
            break
        time.sleep(0.05)

    status = runner.get_status()
    assert status.state == "error"
    assert status.result is not None
    assert status.result.get("login_phase") == "error"
