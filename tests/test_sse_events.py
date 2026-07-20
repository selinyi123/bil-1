from __future__ import annotations

import threading

from fastapi.testclient import TestClient

from web.app import app
from web.event_hub import event_hub
from web.job_runner import JobStatus
from web.sse import format_sse, iter_sse_frames
from unittest.mock import patch


def test_format_sse_is_single_line_data() -> None:
    raw = format_sse("job.progress", {"id": 1, "message": "a\nb"}, event_id=9).decode("utf-8")
    assert "id: 9\n" in raw
    assert "event: job.progress\n" in raw
    assert raw.endswith("\n\n")
    data_line = [line for line in raw.split("\n") if line.startswith("data: ")][0]
    assert "\n" not in data_line[6:]


def test_iter_sse_frames_emits_snapshots_then_events() -> None:
    hub = event_hub
    hub.reset_for_tests()
    frames = iter_sse_frames(
        hub=hub,
        job_snapshot={"id": 1, "state": "idle"},
        auto_snapshot={"state": "idle", "logs": []},
        heartbeat_interval_sec=3600,
    )
    first = next(frames).decode("utf-8")
    second = next(frames).decode("utf-8")
    assert "event: job.snapshot" in first
    assert "event: auto.snapshot" in second

    def _publish_soon() -> None:
        hub.publish("job.created", {"id": 2, "action": "login", "source": "ui", "label": "扫码登录"})

    threading.Timer(0.05, _publish_soon).start()
    third = next(frames).decode("utf-8")
    assert "event: job.created" in third
    frames.close()


def test_api_events_content_type() -> None:
    event_hub.reset_for_tests()
    client = TestClient(app)

    def finite_frames(**kwargs):
        yield format_sse("job.snapshot", {"id": None, "state": "idle"}, event_id=1)
        return

    with patch("web.app.runner.get_status", return_value=JobStatus()), patch(
        "web.app.auto_scheduler.get_status",
        return_value={"state": "idle", "logs": []},
    ), patch("web.sse.iter_sse_frames", side_effect=finite_frames):
        response = client.get("/api/events")
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        assert "job.snapshot" in response.text
