from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import patch

from web.event_hub import event_hub
from web.job_runner import JobRunner


def _drain(sub, timeout: float = 2.0) -> list:
    deadline = time.time() + timeout
    items = []
    while time.time() < deadline:
        try:
            item = sub.queue.get(timeout=0.05)
        except Exception:
            if items:
                break
            continue
        if item is None:
            break
        items.append(item)
        if any(e.event == "job.terminal" for e in items):
            # 再稍等一点收集尾部
            time.sleep(0.05)
            while True:
                try:
                    items.append(sub.queue.get_nowait())
                except Exception:
                    break
            break
    return items


def test_runner_publishes_created_progress_terminal(isolated_home: Path) -> None:
    _ = isolated_home
    event_hub.reset_for_tests()
    sub = event_hub.subscribe()
    runner = JobRunner()
    done = threading.Event()

    def fake_run_action(action, params, *, on_progress, cancel_event):
        on_progress(step=1, total=2, message="进行中", log_append="line-a")
        on_progress(step=2, total=2, message="完成", log_append="line-b")
        done.set()
        return {"ok": True, "message": "ok", "log": "line-a\nline-b"}

    with patch("web.job_runner.run_action", side_effect=fake_run_action):
        job_id = runner.try_start("refresh_status")
        assert job_id is not None
        assert done.wait(timeout=3)

    for _ in range(50):
        if runner.get_status().state != "running":
            break
        time.sleep(0.05)

    events = _drain(sub)
    names = [e.event for e in events]
    assert "job.created" in names
    assert "job.progress" in names
    assert "job.log" in names
    assert "job.terminal" in names
    terminal = [e for e in events if e.event == "job.terminal"][-1]
    assert terminal.data["state"] == "success"
    assert terminal.data["id"] == job_id
    event_hub.unsubscribe(sub)
