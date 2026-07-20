from __future__ import annotations

from fastapi.testclient import TestClient

from src.update_check import UpdateCheckResult
from web.api_contract import API_CONTRACT_HEADER, API_CONTRACT_VERSION
from web.app import app

client = TestClient(app)


def test_updates_check_api_shape(monkeypatch) -> None:
    fake = UpdateCheckResult(
        ok=True,
        current="4.0.2",
        latest="4.0.3",
        update_available=True,
        release_url="https://github.com/luovicter-collab/bilibinggo/releases/tag/v4.0.3",
        download_url=None,
        notes_excerpt="hi",
        message="发现新版本 4.0.3",
        error_kind=None,
        platform="windows",
        hint="请下载 Binggo-Setup-win64.exe 或 Binggo-Portable-win64.zip",
    )
    monkeypatch.setattr("src.update_check.check_for_updates", lambda **kwargs: fake)

    resp = client.post("/api/updates/check")
    assert resp.status_code == 200
    assert resp.headers.get(API_CONTRACT_HEADER) == str(API_CONTRACT_VERSION)
    data = resp.json()
    assert data["ok"] is True
    assert data["current"] == "4.0.2"
    assert data["latest"] == "4.0.3"
    assert data["update_available"] is True
    assert data["platform"] == "windows"
    assert data["message"]


def test_updates_check_api_network_ok_false(monkeypatch) -> None:
    fake = UpdateCheckResult(
        ok=False,
        current="4.0.2",
        latest=None,
        update_available=False,
        release_url="https://github.com/luovicter-collab/bilibinggo/releases",
        download_url=None,
        notes_excerpt=None,
        message="检查更新超时",
        error_kind="network",
        platform="windows",
        hint=None,
    )
    monkeypatch.setattr("src.update_check.check_for_updates", lambda **kwargs: fake)

    resp = client.post("/api/updates/check")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert data["error_kind"] == "network"
