from __future__ import annotations

import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from web.app import app

client = TestClient(app)


def test_reject_unknown_job_action() -> None:
    resp = client.post("/api/jobs", json={"action": "delete_all", "params": {}})
    assert resp.status_code == 400
    data = resp.json()
    assert data["error"]["code"] == "UNSUPPORTED_ACTION"
    assert data["detail"] == data["error"]["message"]


def test_watch_users_api_seeds_and_lists() -> None:
    with patch("web.app.seed_from_candidates_if_empty", return_value=True):
        with patch(
            "web.app.get_watch_users_payload",
            return_value={"count": 1, "users": [{"mid": 1, "name": "u"}], "updated_at": 0},
        ):
            with patch("web.app.get_watch_last_synced_at", return_value=None):
                resp = client.get("/api/watch-users")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert "next_window" in data


def test_participate_triple_job_accepts_filter_params() -> None:
    with patch("web.app.runner.try_start", return_value=1) as start_mock:
        resp = client.post(
            "/api/jobs",
            json={
                "action": "participate_triple",
                "params": {"status": "未参加", "sort": "heat", "order": "desc"},
            },
        )
    assert resp.status_code in (200, 401)
    if resp.status_code == 200:
        start_mock.assert_called_once()
        assert start_mock.call_args.args[0] == "participate_triple"


def test_reject_invalid_dynamic_id() -> None:
    resp = client.post(
        "/api/jobs",
        json={"action": "participate", "params": {"dynamic_id": "not-valid"}},
    )
    assert resp.status_code in (400, 401)


def test_activities_pagination_bounds() -> None:
    resp = client.get("/api/activities", params={"page": 1, "page_size": 20})
    assert resp.status_code == 200
    data = resp.json()
    assert data["page_size"] == 20
    assert "triple_targets" in data
    assert "count" in data["triple_targets"]
    assert "items" in data["triple_targets"]


def test_activities_triple_targets_empty_for_joined_filter() -> None:
    rows = [
        {
            "dynamic_id": "100000000000000001",
            "activity_title": "已参加活动",
            "lottery_type": "转发抽奖",
            "activity_status": "已参加",
            "draw_status": "active",
            "can_participate": False,
            "prize": "奖品",
            "repost_count": 0,
        }
    ]
    with patch("web.activity_service._filtered_activity_rows", return_value=rows):
        resp = client.get("/api/activities", params={"status": "已参加"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["triple_targets"]["count"] == 0
    assert data["triple_targets"]["items"] == []


def test_settings_includes_participate_text_mode() -> None:
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("participate_text_mode") in {"custom", "random_comment"}
    assert data.get("default_participate_fallback_text") == "好运连连！"


def test_save_participate_fallback_text_when_logged_in() -> None:
    with patch("web.app.get_account_profile", return_value={"logged_in": True}):
        resp = client.put(
            "/api/settings/participate-text",
            json={"participate_fallback_text": "好运连连！"},
        )
    assert resp.status_code == 200
    assert resp.json().get("participate_fallback_text") == "好运连连！"


def test_login_qrcode_does_not_crash() -> None:
    resp = client.get("/api/login/qrcode")
    assert resp.status_code in (200, 404)


def test_api_account_does_not_crash() -> None:
    resp = client.get("/api/account")
    assert resp.status_code == 200
    assert "logged_in" in resp.json()


def test_api_account_extras_requires_login_or_returns() -> None:
    resp = client.get("/api/account/extras")
    assert resp.status_code in (200, 401)


# ---------- /api/settings/enhance（P2 #14：强类型校验） ----------


def test_enhance_settings_put_valid_roundtrip(isolated_home) -> None:
    resp = client.put(
        "/api/settings/enhance",
        json={
            "copy_chat": {"enabled": True, "blockwords": ["抽奖", "互关"], "exclude_author": False},
            "at_users": [{"uid": "294887687", "name": "转发抽奖娘"}],
            "topic": "#每日抽奖#",
            "shuffle_targets": True,
            "action_interval_sec": {"min": 0.75, "max": 2.25},
            "partition": {"enabled": False, "name": "抽奖临时关注"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    config = data["config"]
    # uid 归一化为 int，字段结构一一对应
    assert config["at_users"] == [{"uid": 294887687, "name": "转发抽奖娘"}]
    assert config["copy_chat"] == {"enabled": True, "blockwords": ["抽奖", "互关"], "exclude_author": False}
    assert config["action_interval_sec"] == {"min": 0.75, "max": 2.25}
    # 已写盘，GET 回读一致
    get_resp = client.get("/api/settings/enhance")
    assert get_resp.status_code == 200
    assert get_resp.json()["config"] == config


def test_enhance_settings_put_rejects_invalid_range(isolated_home) -> None:
    resp = client.put(
        "/api/settings/enhance",
        json={"action_interval_sec": {"min": 86400, "max": 999999}},
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
    # 消息具体：指出字段与原因
    assert "action_interval_sec" in data["error"]["message"]
    assert "600" in data["error"]["message"]
    # 非法输入未写盘：GET 仍为默认
    get_resp = client.get("/api/settings/enhance")
    assert get_resp.status_code == 200
    assert get_resp.json()["config"]["action_interval_sec"] == {"min": 0.75, "max": 2.25}


def test_enhance_settings_put_rejects_type_error(isolated_home) -> None:
    resp = client.put("/api/settings/enhance", json={"shuffle_targets": "yes"})
    assert resp.status_code == 400
    data = resp.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert "shuffle_targets" in data["error"]["message"]


def test_enhance_settings_put_rejects_bad_at_users(isolated_home) -> None:
    resp = client.put(
        "/api/settings/enhance",
        json={"at_users": [{"uid": "abc", "name": "x"}] * 51},
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"


def test_enhance_settings_get_tolerates_invalid_disk(isolated_home) -> None:
    """磁盘上非法旧配置：GET 不崩溃，非法字段回退默认。"""
    config_path = isolated_home / "config" / "participate_enhance.json"
    config_path.write_text(
        json.dumps({"action_interval_sec": {"min": 86400, "max": 999999}, "topic": 123}),
        encoding="utf-8",
    )
    resp = client.get("/api/settings/enhance")
    assert resp.status_code == 200
    config = resp.json()["config"]
    assert config["action_interval_sec"] == {"min": 0.75, "max": 2.25}
    assert config["topic"] == ""
    assert config["shuffle_targets"] is True


# ---------- /api/accounts/switch（P1 #3：BILI_COOKIE env 覆盖时的文案区分） ----------


def test_switch_account_rejects_under_env_cookie(monkeypatch) -> None:
    """BILI_COOKIE env 生效时切换账号：返回明确错误（不是误导的"账号不存在"）。"""
    monkeypatch.setenv("BILI_COOKIE", "SESSDATA=x; DedeUserID=1001")
    with patch("src.account_pool.set_active", return_value=False):
        resp = client.post("/api/accounts/switch", json={"uid": 1002})
    assert resp.status_code == 400
    data = resp.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert "BILI_COOKIE" in data["error"]["message"]


def test_switch_account_unknown_uid_not_found(monkeypatch) -> None:
    """无 env 且账号不存在：返回 404 账号不存在。"""
    monkeypatch.delenv("BILI_COOKIE", raising=False)
    with patch("src.account_pool.set_active", return_value=False):
        resp = client.post("/api/accounts/switch", json={"uid": 9999})
    assert resp.status_code == 404
    assert "不存在" in resp.json()["error"]["message"]


def test_switch_account_success(monkeypatch) -> None:
    """正常切换：200 + active_uid。"""
    monkeypatch.delenv("BILI_COOKIE", raising=False)
    with patch("src.account_pool.set_active", return_value=True):
        resp = client.post("/api/accounts/switch", json={"uid": 1001})
    assert resp.status_code == 200
    assert resp.json()["active_uid"] == 1001
