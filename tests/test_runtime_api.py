from __future__ import annotations

from fastapi.testclient import TestClient

from web.app import app

client = TestClient(app)


def test_runtime_api_ok() -> None:
    from src.app_paths import __version__

    resp = client.get("/api/runtime")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["version"] == __version__
    assert data["platform"] in {"windows", "macos", "linux", "unknown"}
    assert data["runtime"] in {"dev", "installed", "portable"}
    assert data["data_dir"]
    assert data["bind_host"] == "127.0.0.1"
    assert isinstance(data["findings"], list)
