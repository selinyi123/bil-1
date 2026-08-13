from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from web.actions import DS_HANDLER_BY_ID, REFRESH_SOURCE_TOTAL, run_action
from web.app import app


def test_refresh_source_total_is_four() -> None:
    assert REFRESH_SOURCE_TOTAL == 4
    assert len(DS_HANDLER_BY_ID) == 10


def test_refresh_source_rejects_unknown_id() -> None:
    with pytest.raises(ValueError, match="未知数据源"):
        run_action("refresh_source", {"source_id": "DS-99"})


def test_refresh_source_api_rejects_invalid_id() -> None:
    client = TestClient(app)
    with patch("web.app.get_account_profile", return_value={"logged_in": True}), patch(
        "web.api_errors.is_llm_ready", return_value=True
    ), patch("web.app.runner.try_start", return_value=1) as start_mock:
        resp = client.post("/api/jobs", json={"action": "refresh_source", "params": {"source_id": "DS-0"}})
    assert resp.status_code == 400
    data = resp.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert "无效" in data["detail"]
    start_mock.assert_not_called()


def test_refresh_source_api_accepts_valid_id() -> None:
    client = TestClient(app)
    with patch("web.app.get_account_profile", return_value={"logged_in": True}), patch(
        "web.api_errors.is_llm_ready", return_value=True
    ), patch("web.app.resolve_effective_uid", return_value=999001), patch(
        "web.app.runner.try_start", return_value=1
    ) as start_mock:
        resp = client.post("/api/jobs", json={"action": "refresh_source", "params": {"source_id": "DS-3"}})
    assert resp.status_code == 200
    start_mock.assert_called_once_with(
        "refresh_source", {"source_id": "DS-3"}, source="ui", account_uid="999001"
    )
