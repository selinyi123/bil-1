from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_dev_port_is_8787(monkeypatch):
    monkeypatch.setattr("src.app_paths.is_frozen", lambda: False)
    import importlib

    import src.dashboard_server as dashboard_server

    importlib.reload(dashboard_server)
    assert dashboard_server.get_dashboard_port() == 8787
    assert dashboard_server.DASHBOARD_URL == "http://127.0.0.1:8787"


def test_packaged_port_is_8181(monkeypatch):
    monkeypatch.setattr("src.app_paths.is_frozen", lambda: True)
    import importlib

    import src.dashboard_server as dashboard_server

    importlib.reload(dashboard_server)
    assert dashboard_server.get_dashboard_port() == 8181
    assert dashboard_server.DASHBOARD_URL == "http://127.0.0.1:8181"


def test_run_dashboard_server_restores_none_stdio(monkeypatch):
    import src.dashboard_server as dashboard_server

    monkeypatch.setattr(dashboard_server.sys, "stdout", None)
    monkeypatch.setattr(dashboard_server.sys, "stderr", None)
    captured: dict[str, bool] = {}

    def fake_uvicorn_run(*_args, **_kwargs):
        captured["stdout_ok"] = dashboard_server.sys.stdout is not None
        captured["stderr_ok"] = dashboard_server.sys.stderr is not None

    monkeypatch.setattr("uvicorn.run", fake_uvicorn_run)
    dashboard_server.run_dashboard_server()
    assert captured == {"stdout_ok": True, "stderr_ok": True}
