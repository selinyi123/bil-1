from __future__ import annotations

import json
import logging

from src.app_logging import JsonLineFormatter, reset_logging_for_tests, setup_logging
from src.log_context import job_log_context
from src.log_span import BINGGO_FIELDS_KEY, log_event


def test_jsonl_formatter_includes_context_and_redacts(isolated_home, monkeypatch) -> None:
    reset_logging_for_tests()
    monkeypatch.setattr("src.app_logging.DATA_DIR", isolated_home / "data")
    path = setup_logging(console=False)
    logger = logging.getLogger("binggo.test_fmt")
    with job_log_context(job_id=99, action="refresh_status", job_source="ui"):
        log_event(
            logger,
            "probe SESSDATA=should-hide ok",
            event="job.start",
            component="job",
        )
    text = path.read_text(encoding="utf-8")
    # 最后一行非空
    line = [part for part in text.splitlines() if part.strip()][-1]
    payload = json.loads(line)
    assert payload["v"] == 1
    assert payload["job_id"] == 99
    assert payload["action"] == "refresh_status"
    assert payload["event"] == "job.start"
    assert "should-hide" not in payload["msg"]
    assert "SESSDATA=***" in payload["msg"]
    reset_logging_for_tests()


def test_formatter_fallback_on_bad_record() -> None:
    formatter = JsonLineFormatter()
    record = logging.LogRecord(
        name="binggo.x",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    setattr(record, BINGGO_FIELDS_KEY, {"event": "span.end", "duration_ms": 12})
    line = formatter.format(record)
    payload = json.loads(line)
    assert payload["msg"] == "hello"
    assert payload["duration_ms"] == 12


def test_formatter_includes_exception_stack() -> None:
    formatter = JsonLineFormatter()
    try:
        raise RuntimeError("boom SESSDATA=leak-me")
    except RuntimeError:
        import sys

        record = logging.LogRecord(
            name="binggo.x",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="failed",
            args=(),
            exc_info=sys.exc_info(),
        )
    line = formatter.format(record)
    payload = json.loads(line)
    assert "exc" in payload
    assert "RuntimeError" in payload["exc"]
    assert "leak-me" not in payload["exc"]
    assert "SESSDATA=***" in payload["exc"]
