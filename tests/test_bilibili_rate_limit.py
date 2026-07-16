from __future__ import annotations

import threading
import time

import pytest

from src.bilibili_rate_limit import (
    TokenBucketRateLimiter,
    configure_bilibili_rate_limit,
    reset_bilibili_rate_limit,
)


@pytest.fixture(autouse=True)
def _reset_limiter() -> None:
    reset_bilibili_rate_limit()
    yield
    reset_bilibili_rate_limit()


def test_token_bucket_disabled_when_rps_zero() -> None:
    limiter = TokenBucketRateLimiter(0)
    start = time.monotonic()
    for _ in range(20):
        limiter.acquire()
    assert time.monotonic() - start < 0.05


def test_token_bucket_limits_burst() -> None:
    limiter = TokenBucketRateLimiter(4.0, burst=1.0)
    start = time.monotonic()
    limiter.acquire()
    limiter.acquire()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.2


def test_global_limiter_shared_across_threads() -> None:
    configure_bilibili_rate_limit(rps=5.0)
    from src.bilibili_rate_limit import get_bilibili_rate_limiter

    limiter = get_bilibili_rate_limiter()
    assert limiter.rps == 5.0

    hits: list[float] = []
    lock = threading.Lock()

    def worker() -> None:
        limiter.acquire()
        with lock:
            hits.append(time.monotonic())

    start = time.monotonic()
    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert time.monotonic() - start >= 0.3
    assert len(hits) == 4


def test_bilibili_client_http_methods_acquire_slots(monkeypatch) -> None:
    from src.bilibili_client import BilibiliClient

    calls = {"n": 0}

    def fake_acquire() -> None:
        calls["n"] += 1

    monkeypatch.setattr("src.bilibili_client.acquire_bilibili_request_slot", fake_acquire)

    class _Resp:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"code": 0, "data": {"wbi_img": {"img_url": "a.png", "sub_url": "b.png"}}}

        @property
        def text(self) -> str:
            return "ok"

    client = BilibiliClient(warmup=False)
    client._client.get = lambda *args, **kwargs: _Resp()  # type: ignore[method-assign]
    client._client.post = lambda *args, **kwargs: _Resp()  # type: ignore[method-assign]

    client.get_json("https://api.bilibili.com/x/web-interface/nav")
    client.get_text("https://www.bilibili.com/opus/1")
    client.post_form("https://api.bilibili.com/x/dynamic/feed/dyn/thumb", {"id": "1"})
    client.close()

    assert calls["n"] == 3


def test_default_bilibili_rps_is_three() -> None:
    from src.bilibili_rate_limit import DEFAULT_BILI_RPS, get_bilibili_rate_limiter

    assert DEFAULT_BILI_RPS == 3.0
    assert get_bilibili_rate_limiter().rps == 3.0
