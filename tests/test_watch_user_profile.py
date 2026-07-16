from __future__ import annotations

from src.watch_user_profile import resolve_watch_user_name


class _FakeClient:
    def __init__(self, payloads: list[dict]) -> None:
        self._payloads = list(payloads)
        self.calls = 0

    def request_json(self, url: str, params: dict | None = None, *, referer: str | None = None, retries: int = 3) -> dict:
        del url, params, referer, retries
        payload = self._payloads[min(self.calls, len(self._payloads) - 1)]
        self.calls += 1
        return payload


def test_resolve_watch_user_name_from_card() -> None:
    client = _FakeClient(
        [
            {"code": -799, "message": "请求过于频繁"},
            {"code": 0, "data": {"card": {"name": "测试用户"}}},
        ]
    )
    assert resolve_watch_user_name(client, 123456) == "测试用户"


def test_resolve_watch_user_name_fallback_to_mid() -> None:
    client = _FakeClient(
        [
            {"code": -799, "message": "请求过于频繁"},
            {"code": -404, "message": "用户不存在"},
        ]
    )
    assert resolve_watch_user_name(client, 987654321) == "987654321"
