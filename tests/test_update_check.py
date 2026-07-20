from __future__ import annotations

import httpx

from src.update_check import check_for_updates


class _FakeResp:
    def __init__(self, payload: object, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://api.github.com/")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("error", request=request, response=response)

    def json(self) -> object:
        return self._payload


class _FakeClient:
    def __init__(self, resp: _FakeResp | Exception) -> None:
        self._resp = resp

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def get(self, *args: object, **kwargs: object) -> _FakeResp:
        if isinstance(self._resp, Exception):
            raise self._resp
        return self._resp


def test_check_update_available(monkeypatch) -> None:
    payload = {
        "tag_name": "v4.0.3",
        "html_url": "https://github.com/luovicter-collab/bilibinggo/releases/tag/v4.0.3",
        "body": "notes",
        "assets": [
            {
                "name": "Binggo-Setup-win64.exe",
                "browser_download_url": "https://example.com/setup.exe",
            }
        ],
    }
    monkeypatch.setattr("src.update_check.get_version", lambda: "4.0.2")
    monkeypatch.setattr(
        "src.update_check.httpx.Client",
        lambda **kwargs: _FakeClient(_FakeResp(payload)),
    )
    result = check_for_updates(platform="windows")
    assert result.ok is True
    assert result.update_available is True
    assert result.latest == "4.0.3"
    assert result.download_url == "https://example.com/setup.exe"
    assert "4.0.3" in result.message


def test_check_already_latest(monkeypatch) -> None:
    payload = {
        "tag_name": "v4.0.2",
        "html_url": "https://github.com/example/releases/tag/v4.0.2",
        "body": "",
        "assets": [],
    }
    monkeypatch.setattr("src.update_check.get_version", lambda: "4.0.2")
    monkeypatch.setattr(
        "src.update_check.httpx.Client",
        lambda **kwargs: _FakeClient(_FakeResp(payload)),
    )
    result = check_for_updates(platform="macos")
    assert result.ok is True
    assert result.update_available is False
    assert "最新" in result.message
    assert "dmg" in (result.hint or "").lower() or "macOS-arm64" in (result.hint or "")


def test_check_network_failure(monkeypatch) -> None:
    monkeypatch.setattr("src.update_check.get_version", lambda: "4.0.2")
    monkeypatch.setattr(
        "src.update_check.httpx.Client",
        lambda **kwargs: _FakeClient(httpx.TimeoutException("timeout")),
    )
    result = check_for_updates(platform="windows")
    assert result.ok is False
    assert result.error_kind == "network"
    assert result.update_available is False


def test_check_bad_json(monkeypatch) -> None:
    monkeypatch.setattr("src.update_check.get_version", lambda: "4.0.2")
    monkeypatch.setattr(
        "src.update_check.httpx.Client",
        lambda **kwargs: _FakeClient(_FakeResp(["not", "a", "dict"])),
    )
    result = check_for_updates()
    assert result.ok is False
    assert result.error_kind == "parse"


def test_check_http_status_friendly(monkeypatch) -> None:
    request = httpx.Request("GET", "https://api.github.com/")
    response = httpx.Response(404, request=request)
    err = httpx.HTTPStatusError("missing", request=request, response=response)

    class _BoomClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get(self, *args, **kwargs):
            raise err

    monkeypatch.setattr("src.update_check.get_version", lambda: "4.0.2")
    monkeypatch.setattr("src.update_check.httpx.Client", lambda **kwargs: _BoomClient())
    result = check_for_updates(platform="windows")
    assert result.ok is False
    assert result.error_kind == "network"
    assert "Release" in result.message
    assert "404" not in result.message
