from __future__ import annotations

from fastapi.testclient import TestClient

from web.app import app

client = TestClient(app)


def test_reject_unknown_job_action() -> None:
    resp = client.post("/api/jobs", json={"action": "delete_all", "params": {}})
    assert resp.status_code == 400


def test_reject_invalid_dynamic_id() -> None:
    resp = client.post(
        "/api/jobs",
        json={"action": "participate", "params": {"dynamic_id": "not-valid"}},
    )
    assert resp.status_code in (400, 401)


def test_activities_pagination_bounds() -> None:
    resp = client.get("/api/activities", params={"page": 1, "page_size": 100})
    assert resp.status_code == 200
    data = resp.json()
    assert data["page_size"] <= 100


def test_login_qrcode_does_not_crash() -> None:
    resp = client.get("/api/login/qrcode")
    assert resp.status_code in (200, 404)


def test_api_account_does_not_crash() -> None:
    resp = client.get("/api/account")
    assert resp.status_code == 200
    assert "logged_in" in resp.json()
