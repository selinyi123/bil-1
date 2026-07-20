from __future__ import annotations

import queue

from web.event_hub import EventHub


def test_publish_broadcasts_to_subscribers() -> None:
    hub = EventHub(queue_maxsize=16)
    a = hub.subscribe()
    b = hub.subscribe()
    seq = hub.publish("job.progress", {"id": 1, "step": 1})
    assert seq == 1
    ea = a.queue.get_nowait()
    eb = b.queue.get_nowait()
    assert ea.event == "job.progress"
    assert ea.data["id"] == 1
    assert ea.data["seq"] == 1
    assert eb.seq == ea.seq
    hub.unsubscribe(a)
    hub.unsubscribe(b)


def test_overflow_keeps_terminal() -> None:
    hub = EventHub(queue_maxsize=8)
    sub = hub.subscribe()
    for i in range(40):
        hub.publish("job.progress", {"id": 1, "step": i})
    hub.publish("job.terminal", {"id": 1, "state": "success", "message": "ok"})
    events = []
    while True:
        try:
            events.append(sub.queue.get_nowait())
        except queue.Empty:
            break
    terminals = [e for e in events if e and e.event == "job.terminal"]
    assert len(terminals) == 1
    assert terminals[0].data["state"] == "success"
    hub.unsubscribe(sub)


def test_overflow_keeps_fatal_snapshot_and_latest_auto_log() -> None:
    hub = EventHub(queue_maxsize=6)
    sub = hub.subscribe()
    for i in range(20):
        hub.publish("job.progress", {"id": 1, "step": i})
        hub.publish("auto.log", {"message": f"log-{i}", "level": "info"})
    hub.publish("auto.snapshot", {"state": "fatal", "fatal_error": "撞车", "message": "停机"})
    events = []
    while True:
        try:
            events.append(sub.queue.get_nowait())
        except queue.Empty:
            break
    snapshots = [e for e in events if e and e.event == "auto.snapshot"]
    logs = [e for e in events if e and e.event == "auto.log"]
    assert any(e.data.get("state") == "fatal" for e in snapshots)
    assert logs
    assert logs[-1].data["message"].startswith("log-")
    hub.unsubscribe(sub)


def test_unsubscribe_stops_delivery() -> None:
    hub = EventHub()
    sub = hub.subscribe()
    hub.unsubscribe(sub)
    hub.publish("job.created", {"id": 2})
    try:
        item = sub.queue.get_nowait()
    except queue.Empty:
        item = "empty"
    # close 可能放入 None 毒丸
    assert item in (None, "empty")


def test_subscribe_evicts_oldest_when_at_limit() -> None:
    hub = EventHub(queue_maxsize=4, max_subscribers=2)
    first = hub.subscribe()
    second = hub.subscribe()
    third = hub.subscribe()
    assert first.closed is True
    hub.publish("job.progress", {"id": 1, "step": 1})
    # close() 会放入毒丸；已关闭订阅者不应再收到业务事件
    drained = []
    while True:
        try:
            drained.append(first.queue.get_nowait())
        except queue.Empty:
            break
    assert all(item is None for item in drained)
    assert second.queue.get_nowait().data["step"] == 1
    assert third.queue.get_nowait().data["step"] == 1
    hub.unsubscribe(second)
    hub.unsubscribe(third)


def test_close_enqueues_sentinel_when_room() -> None:
    hub = EventHub(queue_maxsize=4)
    sub = hub.subscribe()
    hub.publish("job.progress", {"id": 1, "step": 1})
    sub.close()
    items = []
    while True:
        try:
            items.append(sub.queue.get_nowait())
        except queue.Empty:
            break
    assert any(item is None for item in items)
    hub.unsubscribe(sub)


def test_closed_subscriber_ignores_further_publish() -> None:
    hub = EventHub(queue_maxsize=4)
    sub = hub.subscribe()
    for i in range(4):
        hub.publish("job.progress", {"id": 1, "step": i})
    sub.close()
    before = sub.queue.qsize()
    hub.publish("job.progress", {"id": 1, "step": 99})
    hub.publish("job.terminal", {"id": 1, "state": "success"})
    assert sub.closed is True
    assert sub.queue.qsize() == before
    hub.unsubscribe(sub)


def test_concurrent_publish_does_not_raise() -> None:
    import threading

    hub = EventHub(queue_maxsize=8)
    sub = hub.subscribe()
    errors: list[BaseException] = []

    def worker(start: int) -> None:
        try:
            for i in range(40):
                hub.publish("job.progress", {"id": 1, "step": start + i})
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i * 100,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    hub.publish("job.terminal", {"id": 1, "state": "success"})
    events = []
    while True:
        try:
            events.append(sub.queue.get_nowait())
        except queue.Empty:
            break
    assert any(e and e.event == "job.terminal" for e in events)
    hub.unsubscribe(sub)
