"""Job 日志上下文（contextvars），供 Formatter / Filter 自动注入字段。"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any, Iterator

_job_id: ContextVar[int | None] = ContextVar("binggo_job_id", default=None)
_action: ContextVar[str | None] = ContextVar("binggo_job_action", default=None)
_job_source: ContextVar[str | None] = ContextVar("binggo_job_source", default=None)


@dataclass(frozen=True)
class TokenBundle:
    job_id: Token
    action: Token
    job_source: Token


def bind_job(*, job_id: int, action: str, job_source: str) -> TokenBundle:
    return TokenBundle(
        job_id=_job_id.set(int(job_id)),
        action=_action.set(str(action or "")),
        job_source=_job_source.set(str(job_source or "ui")),
    )


def reset_job(tokens: TokenBundle) -> None:
    _job_id.reset(tokens.job_id)
    _action.reset(tokens.action)
    _job_source.reset(tokens.job_source)


def get_context_fields() -> dict[str, Any]:
    fields: dict[str, Any] = {}
    job_id = _job_id.get()
    if job_id is not None:
        fields["job_id"] = int(job_id)
    action = _action.get()
    if action:
        fields["action"] = action
    job_source = _job_source.get()
    if job_source:
        fields["job_source"] = job_source
    return fields


@contextmanager
def job_log_context(*, job_id: int, action: str, job_source: str) -> Iterator[None]:
    tokens = bind_job(job_id=job_id, action=action, job_source=job_source)
    try:
        yield
    finally:
        reset_job(tokens)
