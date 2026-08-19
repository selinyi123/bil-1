from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from src.diagnostics import build_diagnostics_bundle
from web.app import app

client = TestClient(app)


def test_slim_auto_status_uses_scheduler_fields() -> None:
    text = build_diagnostics_bundle(
        auto_status={
            "state": "running",
            "state_label": "运行中",
            "message": "调度器运行中",
            "fatal_error": None,
            "current_phase": "等待下一刻度",
            "next_hint": "下一刻 12:00",
            "logs": [{"ts": "t", "level": "info", "message": "ok SESSDATA=auto-secret"}],
            "enabled": True,  # 旧字段，不应出现在导出正文关键路径上
            "running": True,
        }
    )["text"]
    assert "state': 'running'" in text or "running" in text
    assert "等待下一刻度" in text
    assert "auto-secret" not in text
    assert "SESSDATA=***" in text


def test_diagnostics_logs_ok(isolated_home, monkeypatch) -> None:
    log_path = isolated_home / "data" / "logs" / "binggo.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        '{"v":1,"job_id":3,"msg":"hello SESSDATA=secret123"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr("src.log_query.log_file", lambda: log_path)
    monkeypatch.setattr("src.log_query.log_dir", lambda: log_path.parent)

    resp = client.get("/api/diagnostics/logs", params={"job_id": 3, "limit": 20})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["count"] >= 1
    assert isinstance(data["lines"], list)
    assert data["lines"][0]["job_id"] == 3
    # 读侧脱敏：即使文件里是明文
    assert "secret123" not in str(data["lines"][0])


def test_diagnostics_logs_limit_validation() -> None:
    resp = client.get("/api/diagnostics/logs", params={"limit": 9999})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_diagnostics_bundle_redacts(isolated_home, monkeypatch) -> None:
    log_path = isolated_home / "data" / "logs" / "binggo.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        '{"v":1,"msg":"leak SESSDATA=super-secret-cookie"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr("src.log_query.log_file", lambda: log_path)
    monkeypatch.setattr("src.log_query.log_dir", lambda: log_path.parent)

    with patch("web.app.runner.get_status") as status_mock:
        status_mock.return_value.to_dict.return_value = {
            "id": 1,
            "state": "idle",
            "action": "",
            "message": "",
        }
        resp = client.get("/api/diagnostics/bundle")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["filename"].startswith("binggo-diagnostics-")
    assert "super-secret-cookie" not in data["text"]
    assert "SESSDATA=***" in data["text"] or "***" in data["text"]
