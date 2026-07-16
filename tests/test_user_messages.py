from __future__ import annotations

from web.user_messages import friendly_error, sanitize_log


def test_sanitize_log_keeps_summary_when_traceback_present() -> None:
    log = (
        "=== DS-1 检查 ===\n"
        "无新专栏，使用缓存\n"
        "Traceback (most recent call last):\n"
        '  File "foo.py", line 1, in <module>\n'
        "NameError: boom\n"
        "=== 合并去重 ===\n"
        "合计 311 条"
    )
    cleaned = sanitize_log(log)
    assert "DS-1" in cleaned
    assert "合并去重" in cleaned
    assert "Traceback" not in cleaned
    assert "NameError" not in cleaned
    assert cleaned != "任务执行时发生内部错误，请稍后重试"


def test_friendly_error_hides_traceback() -> None:
    exc = RuntimeError("Traceback (most recent call last):\n  File foo.py")
    assert "Traceback" not in friendly_error(exc)


def test_friendly_error_invalid_dynamic_id() -> None:
    assert friendly_error(ValueError("活动 ID 无效")) == "未找到活动信息，请刷新页面后重试"


def test_sanitize_log_strips_uvicorn_stack() -> None:
    log = (
        "=== DS-2 检查 ===\n"
        "无新专栏，使用缓存，链接 137 条，保留缓存\n"
        "OSError: [Errno 22] Invalid argument\n"
        '  File "scripts/run_dashboard.py", line 26, in main\n'
        '    run_dashboard_server()\n'
        "    server.run()\n"
    )
    cleaned = sanitize_log(log)
    assert "DS-2" in cleaned
    assert "OSError" not in cleaned
    assert "uvicorn" not in cleaned


def test_sanitize_log_strips_paths() -> None:
    log = "=== 保存 ===\nC:\\Users\\me\\data\\output\\enriched_latest.json"
    cleaned = sanitize_log(log)
    assert "C:\\Users" not in cleaned
    assert "[本地文件]" in cleaned or "保存" in cleaned
