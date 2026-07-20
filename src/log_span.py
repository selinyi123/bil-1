"""结构化 span / 事件日志 helper。"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Iterator

from src.app_logging import get_logger

_EXTRA_KEY = "binggo_fields"
_MAX_EXTRA_KEYS = 16
_MAX_EXTRA_STR = 500


def _clip_extra(extra: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for index, (key, value) in enumerate(extra.items()):
        if index >= _MAX_EXTRA_KEYS:
            break
        key_s = str(key)[:64]
        if isinstance(value, str) and len(value) > _MAX_EXTRA_STR:
            out[key_s] = value[:_MAX_EXTRA_STR] + "…"
        elif isinstance(value, (str, int, float, bool)) or value is None:
            out[key_s] = value
        else:
            try:
                text = str(value)
            except Exception:
                text = "<unserializable>"
            if len(text) > _MAX_EXTRA_STR:
                text = text[:_MAX_EXTRA_STR] + "…"
            out[key_s] = text
    return out


def log_event(
    logger: logging.Logger,
    msg: str,
    *,
    level: int = logging.INFO,
    event: str | None = None,
    component: str | None = None,
    source_id: str | None = None,
    phase: str | None = None,
    duration_ms: int | None = None,
    error_kind: str | None = None,
    **extra: Any,
) -> None:
    fields: dict[str, Any] = {}
    if event:
        fields["event"] = event
    if component:
        fields["component"] = component
    if source_id:
        fields["source_id"] = source_id
    if phase:
        fields["phase"] = phase
    if duration_ms is not None:
        fields["duration_ms"] = int(duration_ms)
    if error_kind:
        fields["error_kind"] = error_kind
    if extra:
        fields["extra"] = _clip_extra(extra)
    # context 字段由 Filter/Formatter 合并；此处只放事件字段
    logger.log(level, msg, extra={_EXTRA_KEY: fields})


@contextmanager
def log_span(
    name: str,
    *,
    logger: logging.Logger | None = None,
    component: str | None = None,
    source_id: str | None = None,
    phase: str | None = None,
    **extra: Any,
) -> Iterator[None]:
    log = logger or get_logger("span")
    started = time.perf_counter()
    log_event(
        log,
        f"span start: {name}",
        event="span.start",
        component=component,
        source_id=source_id,
        phase=phase,
        span=name,
        **extra,
    )
    exc_name: str | None = None
    try:
        yield
    except Exception as exc:
        exc_name = type(exc).__name__
        raise
    finally:
        duration_ms = int((time.perf_counter() - started) * 1000)
        end_extra = dict(extra)
        if exc_name:
            end_extra["error_type"] = exc_name
        log_event(
            log,
            f"span end: {name}",
            level=logging.ERROR if exc_name else logging.INFO,
            event="span.end",
            component=component,
            source_id=source_id,
            phase=phase,
            duration_ms=duration_ms,
            span=name,
            **end_extra,
        )


class PhaseSpanTracker:
    """跨 progress 回调跟踪 pipeline 子阶段耗时。"""

    def __init__(
        self,
        *,
        logger: logging.Logger | None = None,
        component: str = "pipeline",
    ) -> None:
        self._logger = logger or get_logger("span")
        self._component = component
        self._phase: str | None = None
        self._started: float | None = None
        self._name: str | None = None

    def set_phase(self, phase: str, *, name: str | None = None) -> None:
        if self._phase == phase:
            return
        self.close()
        self._phase = phase
        self._name = name or phase
        self._started = time.perf_counter()
        log_event(
            self._logger,
            f"span start: {self._name}",
            event="span.start",
            component=self._component,
            phase=phase,
            span=self._name,
        )

    def close(self, *, error_kind: str | None = None) -> None:
        if self._phase is None or self._started is None:
            return
        duration_ms = int((time.perf_counter() - self._started) * 1000)
        log_event(
            self._logger,
            f"span end: {self._name}",
            level=logging.ERROR if error_kind else logging.INFO,
            event="span.end",
            component=self._component,
            phase=self._phase,
            duration_ms=duration_ms,
            error_kind=error_kind,
            span=self._name or self._phase,
        )
        self._phase = None
        self._started = None
        self._name = None


# 供 Formatter 识别
BINGGO_FIELDS_KEY = _EXTRA_KEY
