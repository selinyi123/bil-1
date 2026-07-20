from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from web.api_contract import API_CONTRACT_HEADER, API_CONTRACT_VERSION
from web.app import app

client = TestClient(app)


def _assert_error_shape(resp, *, code: str, status: int) -> dict:
    assert resp.status_code == status
    assert resp.headers.get(API_CONTRACT_HEADER) == str(API_CONTRACT_VERSION)
    data = resp.json()
    assert "error" in data
    assert data["error"]["code"] == code
    assert isinstance(data["error"]["message"], str) and data["error"]["message"]
    assert data["detail"] == data["error"]["message"]
    return data


def test_json_api_success_has_contract_header() -> None:
    resp = client.get("/api/account")
    assert resp.status_code == 200
    assert resp.headers.get(API_CONTRACT_HEADER) == str(API_CONTRACT_VERSION)


def test_unsupported_action_error_code() -> None:
    resp = client.post("/api/jobs", json={"action": "delete_all", "params": {}})
    _assert_error_shape(resp, code="UNSUPPORTED_ACTION", status=400)


def test_validation_error_becomes_400_not_422() -> None:
    resp = client.post("/api/watch-users", json={"mid": "abc"})
    data = _assert_error_shape(resp, code="VALIDATION_ERROR", status=400)
    assert data["error"]["detail"] is not None
    # 用户可读文案应去掉 Pydantic「Value error, 」前缀
    assert "MID 无效" in data["error"]["message"]
    assert not data["error"]["message"].lower().startswith("value error")


def test_openapi_includes_error_body_and_contract() -> None:
    schema = client.get("/openapi.json").json()
    assert schema["info"].get("x-api-contract") == API_CONTRACT_VERSION
    assert "ErrorBody" in schema["components"]["schemas"]


def test_sse_response_has_contract_header() -> None:
    from unittest.mock import patch

    from web.sse import format_sse

    def finite_frames(**kwargs):
        yield format_sse("heartbeat", {"ts": 1})
        return

    with patch("web.sse.iter_sse_frames", side_effect=finite_frames):
        resp = client.get("/api/events")
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
    assert resp.headers.get(API_CONTRACT_HEADER) == str(API_CONTRACT_VERSION)


def test_unknown_error_code_coerces_to_internal() -> None:
    from web.api_errors import AppError, ErrorCode

    err = AppError("NOT_A_REAL_CODE", "boom")
    assert err.code == ErrorCode.INTERNAL
    assert err.status_code == 500


def test_auth_required_for_watch_add() -> None:
    with patch("web.app.get_account_profile", return_value={"logged_in": False}):
        resp = client.post("/api/watch-users", json={"mid": 123456})
    _assert_error_shape(resp, code="AUTH_REQUIRED", status=401)


def test_llm_not_ready_distinct_from_auth() -> None:
    with patch("web.app.get_account_profile", return_value={"logged_in": True}), patch(
        "web.api_errors.is_llm_ready",
        return_value=False,
    ), patch("web.app.runner.try_start", return_value=1):
        resp = client.post("/api/jobs", json={"action": "refresh_all", "params": {}})
    _assert_error_shape(resp, code="LLM_NOT_READY", status=401)


def test_auth_required_for_refresh_status_job() -> None:
    with patch("web.app.get_account_profile", return_value={"logged_in": False}), patch(
        "web.app.runner.try_start", return_value=1
    ) as start_mock:
        resp = client.post("/api/jobs", json={"action": "refresh_status", "params": {}})
    _assert_error_shape(resp, code="AUTH_REQUIRED", status=401)
    start_mock.assert_not_called()


def test_refresh_status_ok_without_llm() -> None:
    """refresh_status 需登录、不需 LLM；就绪后应 try_start。"""
    with patch("web.app.get_account_profile", return_value={"logged_in": True}), patch(
        "web.api_errors.is_llm_ready",
        return_value=False,
    ), patch("web.app.runner.try_start", return_value=42) as start_mock, patch(
        "web.app.runner.get_status"
    ) as status_mock:
        status_mock.return_value.to_dict.return_value = {
            "id": 42,
            "state": "running",
            "action": "refresh_status",
        }
        resp = client.post("/api/jobs", json={"action": "refresh_status", "params": {}})
    assert resp.status_code == 200
    assert resp.headers.get(API_CONTRACT_HEADER) == str(API_CONTRACT_VERSION)
    data = resp.json()
    assert data["ok"] is True
    assert data["job"]["id"] == 42
    start_mock.assert_called_once()
    assert start_mock.call_args.args[0] == "refresh_status"


def test_job_ready_refresh_all_starts() -> None:
    with patch("web.app.get_account_profile", return_value={"logged_in": True}), patch(
        "web.api_errors.is_llm_ready",
        return_value=True,
    ), patch("web.app.runner.try_start", return_value=7) as start_mock, patch(
        "web.app.runner.get_status"
    ) as status_mock:
        status_mock.return_value.to_dict.return_value = {
            "id": 7,
            "state": "running",
            "action": "refresh_all",
        }
        resp = client.post("/api/jobs", json={"action": "refresh_all", "params": {}})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    start_mock.assert_called_once()
    assert start_mock.call_args.args[0] == "refresh_all"


def test_job_busy_error_code() -> None:
    with patch("web.app.get_account_profile", return_value={"logged_in": True}), patch(
        "web.api_errors.is_llm_ready",
        return_value=True,
    ), patch("web.app.runner.try_start", return_value=None):
        resp = client.post("/api/jobs", json={"action": "refresh_status", "params": {}})
    _assert_error_shape(resp, code="JOB_BUSY", status=409)


def test_job_not_cancellable_error_code() -> None:
    with patch("web.app.runner.cancel", return_value=False):
        resp = client.post("/api/jobs/cancel")
    _assert_error_shape(resp, code="JOB_NOT_CANCELLABLE", status=409)


def test_auto_already_running_error_code() -> None:
    with patch("web.app.auto_scheduler.start", side_effect=RuntimeError("调度器已在运行")):
        resp = client.post("/api/auto/start")
    _assert_error_shape(resp, code="AUTO_ALREADY_RUNNING", status=409)


def test_qrcode_not_found_error_code() -> None:
    with patch("web.app.QR_IMAGE_PATH") as path_mock:
        path_mock.exists.return_value = False
        resp = client.get("/api/login/qrcode")
    _assert_error_shape(resp, code="NOT_FOUND", status=404)
