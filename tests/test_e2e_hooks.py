"""E2E 钩子：默认 no-op；BINGGO_E2E=1 时可装到独立 FastAPI 实例。"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_install_noop_without_flag(monkeypatch) -> None:
    monkeypatch.delenv("BINGGO_E2E", raising=False)
    from web import e2e_hooks as hooks

    assert hooks.e2e_enabled() is False
    app = FastAPI()
    prev_installed = hooks._INSTALLED
    hooks._INSTALLED = False
    try:
        hooks.install_e2e_hooks(app)
        paths = [getattr(route, "path", "") for route in app.routes]
        assert not any("/api/testing" in path for path in paths)
    finally:
        hooks._INSTALLED = prev_installed


def test_install_and_state_roundtrip(monkeypatch) -> None:
    monkeypatch.setenv("BINGGO_E2E", "1")
    from web import e2e_hooks as hooks

    assert hooks.e2e_enabled() is True
    hooks.set_e2e_state(account="logged_out", llm="not_ready")
    prev_installed = hooks._INSTALLED
    hooks._INSTALLED = False
    hooks._ORIGINALS.clear()

    app = FastAPI()
    try:
        hooks.install_e2e_hooks(app)
        client = TestClient(app)

        get_resp = client.get("/api/testing/e2e-state")
        assert get_resp.status_code == 200
        assert get_resp.json()["state"]["account"] == "logged_out"

        post_resp = client.post(
            "/api/testing/e2e-state",
            json={"account": "logged_in", "llm": "ready"},
        )
        assert post_resp.status_code == 200
        assert post_resp.json()["state"] == {"account": "logged_in", "llm": "ready"}

        profile = hooks._mock_account_profile()
        assert profile["logged_in"] is True
        assert profile["at_alert"] == {
            "increased": False,
            "delta": 0,
            "previous": 0,
            "current": 0,
        }
        extras = hooks._mock_account_extras()
        assert extras["at_alert"]["increased"] is False
        assert hooks._mock_is_llm_ready() is True
    finally:
        hooks.uninstall_e2e_hooks()
        hooks._INSTALLED = prev_installed


def test_mock_profile_logged_out_shape() -> None:
    from web import e2e_hooks as hooks

    hooks.set_e2e_state(account="logged_out", llm="not_ready")
    profile = hooks._mock_account_profile()
    assert profile["logged_in"] is False
    assert "increased" in profile["at_alert"]
    assert profile["extras_loading"] is False
