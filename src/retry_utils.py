from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def retry_call(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 1.0,
    multiplier: float = 2.0,
    retry_on: Callable[[BaseException], bool] | None = None,
) -> T:
    last_error: BaseException | None = None
    for attempt in range(max(1, attempts)):
        try:
            return fn()
        except BaseException as exc:
            last_error = exc
            if attempt >= attempts - 1:
                break
            if retry_on is not None and not retry_on(exc):
                break
            time.sleep(base_delay * (multiplier**attempt))
    assert last_error is not None
    raise last_error


def is_transient_http_error(exc: BaseException) -> bool:
    import httpx

    if isinstance(exc, httpx.RequestError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {408, 429, 500, 502, 503, 504}
    return False
