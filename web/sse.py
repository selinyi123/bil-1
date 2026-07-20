"""SSE 编码与 StreamingResponse 生成器。"""

from __future__ import annotations

import json
import queue
import time
from collections.abc import Iterator
from typing import Any

from starlette.responses import StreamingResponse

from web.event_hub import EventHub, HubEvent, Subscriber, event_hub

HEARTBEAT_INTERVAL_SEC = 15.0
QUEUE_GET_TIMEOUT_SEC = 1.0


def format_sse(event: str, data: dict[str, Any], *, event_id: int | None = None) -> bytes:
    lines: list[str] = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    lines.append(f"data: {payload}")
    lines.append("")
    lines.append("")
    return "\n".join(lines).encode("utf-8")


def _trim_auto_logs(status: dict[str, Any], *, limit: int = 30) -> dict[str, Any]:
    out = dict(status)
    logs = out.get("logs")
    if isinstance(logs, list) and len(logs) > limit:
        out["logs"] = logs[-limit:]
    return out


def iter_sse_frames(
    *,
    hub: EventHub | None = None,
    job_snapshot: dict[str, Any] | None = None,
    auto_snapshot: dict[str, Any] | None = None,
    heartbeat_interval_sec: float = HEARTBEAT_INTERVAL_SEC,
) -> Iterator[bytes]:
    bus = hub or event_hub
    sub: Subscriber = bus.subscribe()
    last_heartbeat = time.monotonic()
    try:
        if job_snapshot is not None:
            frame = dict(job_snapshot)
            frame.setdefault("ts", int(time.time()))
            yield format_sse("job.snapshot", frame, event_id=frame.get("seq"))
        if auto_snapshot is not None:
            frame = _trim_auto_logs(auto_snapshot)
            frame.setdefault("ts", int(time.time()))
            yield format_sse("auto.snapshot", frame, event_id=frame.get("seq"))
        while True:
            if sub.closed:
                break
            now = time.monotonic()
            if now - last_heartbeat >= heartbeat_interval_sec:
                hb = {"ts": int(time.time())}
                yield format_sse("heartbeat", hb)
                last_heartbeat = now
            try:
                item: HubEvent | None = sub.queue.get(timeout=QUEUE_GET_TIMEOUT_SEC)
            except queue.Empty:
                continue
            if item is None or sub.closed:
                break
            yield format_sse(item.event, item.data, event_id=item.seq)
    finally:
        bus.unsubscribe(sub)


def sse_response(
    *,
    job_snapshot: dict[str, Any] | None = None,
    auto_snapshot: dict[str, Any] | None = None,
    hub: EventHub | None = None,
) -> StreamingResponse:
    generator = iter_sse_frames(
        hub=hub,
        job_snapshot=job_snapshot,
        auto_snapshot=auto_snapshot,
    )
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
