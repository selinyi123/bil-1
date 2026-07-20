"""进程内事件总线：供 SSE 广播 Job / Auto 实时事件。"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from typing import Any

from src.app_logging import get_logger

logger = get_logger("events")

QUEUE_MAXSIZE = 256
MAX_SUBSCRIBERS = 32
_PROTECTED_EVENTS = frozenset({"job.terminal"})


def _is_protected(event: str, data: dict[str, Any]) -> bool:
    if event in _PROTECTED_EVENTS:
        return True
    if event == "auto.snapshot":
        state = str(data.get("state") or "")
        if state in {"fatal", "stopped"}:
            return True
        if data.get("fatal_error"):
            return True
    return False


def _is_droppable(event: str) -> bool:
    return event in {
        "job.progress",
        "job.log",
        "job.created",
        "job.snapshot",
        "auto.snapshot",
        "auto.log",
    }


@dataclass
class HubEvent:
    seq: int
    event: str
    data: dict[str, Any]


class Subscriber:
    def __init__(self, maxsize: int = QUEUE_MAXSIZE) -> None:
        self.queue: queue.Queue[HubEvent | None] = queue.Queue(maxsize=maxsize)
        self.closed = False
        self._lock = threading.Lock()

    def close(self) -> None:
        with self._lock:
            self.closed = True
            try:
                self.queue.put_nowait(None)
            except queue.Full:
                # 队列满时毒丸放不进；消费者以 closed 标志退出
                pass


class EventHub:
    def __init__(
        self,
        *,
        queue_maxsize: int = QUEUE_MAXSIZE,
        max_subscribers: int = MAX_SUBSCRIBERS,
    ) -> None:
        self._lock = threading.Lock()
        self._subs: list[Subscriber] = []
        self._seq = 0
        self._queue_maxsize = queue_maxsize
        self._max_subscribers = max(1, int(max_subscribers))

    def reset_for_tests(self) -> None:
        with self._lock:
            for sub in self._subs:
                sub.close()
            self._subs.clear()
            self._seq = 0

    def subscribe(self) -> Subscriber:
        sub = Subscriber(maxsize=self._queue_maxsize)
        with self._lock:
            # 多标签页无限订阅会撑内存：踢掉最旧连接
            while len(self._subs) >= self._max_subscribers:
                oldest = self._subs.pop(0)
                oldest.close()
                logger.warning("SSE 订阅数达上限 %s，已关闭最旧连接", self._max_subscribers)
            self._subs.append(sub)
        return sub

    def unsubscribe(self, sub: Subscriber) -> None:
        sub.close()
        with self._lock:
            self._subs = [item for item in self._subs if item is not sub]

    def publish(self, event: str, data: dict[str, Any] | None = None) -> int:
        payload = dict(data or {})
        with self._lock:
            self._seq += 1
            seq = self._seq
            payload.setdefault("ts", int(time.time()))
            payload["seq"] = seq
            hub_event = HubEvent(seq=seq, event=event, data=payload)
            subs = list(self._subs)
        for sub in subs:
            self._enqueue(sub, hub_event)
        return seq

    def _enqueue(self, sub: Subscriber, hub_event: HubEvent) -> None:
        with sub._lock:
            if sub.closed:
                return
            try:
                sub.queue.put_nowait(hub_event)
                return
            except queue.Full:
                pass
            self._make_room_locked(sub, hub_event)
            if sub.closed:
                return
            try:
                sub.queue.put_nowait(hub_event)
            except queue.Full:
                if _is_protected(hub_event.event, hub_event.data):
                    logger.warning(
                        "事件队列仍满，丢弃 protected 失败 event=%s seq=%s",
                        hub_event.event,
                        hub_event.seq,
                    )

    def _make_room_locked(self, sub: Subscriber, incoming: HubEvent) -> None:
        """丢最旧可丢事件；尽量保留 terminal / fatal snapshot / 最新 auto.log。

        调用方须已持有 sub._lock。
        """
        buffered: list[HubEvent] = []
        saw_close = False
        while True:
            try:
                item = sub.queue.get_nowait()
            except queue.Empty:
                break
            if item is None:
                saw_close = True
                continue
            buffered.append(item)

        if saw_close:
            sub.closed = True

        protected: list[HubEvent] = []
        droppable: list[HubEvent] = []
        last_auto_log: HubEvent | None = None
        for item in buffered:
            if item.event == "auto.log":
                last_auto_log = item
                continue
            if _is_protected(item.event, item.data):
                protected.append(item)
            elif _is_droppable(item.event):
                droppable.append(item)
            else:
                protected.append(item)

        keep = list(protected)
        if last_auto_log is not None:
            keep.append(last_auto_log)

        # 为 incoming 预留 1 格；若仍有空位，从旧到新回填较新的 droppable
        reserve = 0 if sub.closed else 1
        room = max(0, self._queue_maxsize - len(keep) - reserve)
        if room > 0 and droppable:
            keep.extend(droppable[-room:])

        if (
            not sub.closed
            and not _is_protected(incoming.event, incoming.data)
            and len(keep) >= self._queue_maxsize
        ):
            keep = [
                item
                for item in keep
                if _is_protected(item.event, item.data) or item.event == "auto.log"
            ]
            if last_auto_log is not None and last_auto_log not in keep:
                keep.append(last_auto_log)

        limit = self._queue_maxsize - reserve
        for item in keep[: max(0, limit)]:
            try:
                sub.queue.put_nowait(item)
            except queue.Full:
                break

        if sub.closed:
            try:
                sub.queue.put_nowait(None)
            except queue.Full:
                pass


event_hub = EventHub()
