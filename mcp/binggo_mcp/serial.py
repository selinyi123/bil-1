"""Process-wide serial lock: all MCP tools run one at a time (H1)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")

TOOL_LOCK = asyncio.Lock()


def with_serial_lock(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        async with TOOL_LOCK:
            return await func(*args, **kwargs)

    return wrapper
