from __future__ import annotations

from web.user_messages import friendly_error, sanitize_log


def test_friendly_error_hides_traceback() -> None:
    exc = RuntimeError("Traceback (most recent call last):\n  File foo.py")
    assert "Traceback" not in friendly_error(exc)


def test_friendly_error_invalid_dynamic_id() -> None:
    assert friendly_error(ValueError("活动 ID 无效")) == "未找到活动信息，请刷新页面后重试"


def test_sanitize_log_strips_paths() -> None:
    log = "=== 保存 ===\nC:\\Users\\me\\data\\output\\enriched_latest.json"
    cleaned = sanitize_log(log)
    assert "C:\\Users" not in cleaned
    assert "[本地文件]" in cleaned or "保存" in cleaned
