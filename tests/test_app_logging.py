from __future__ import annotations

import json

from src.app_logging import get_logger, reset_logging_for_tests, setup_logging


def test_setup_logging_creates_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("src.app_logging.DATA_DIR", tmp_path)
    reset_logging_for_tests()

    path = setup_logging(console=False)
    assert path == tmp_path / "logs" / "binggo.log"
    assert path.exists()

    child = get_logger("test")
    child.info("hello from test")
    content = path.read_text(encoding="utf-8")
    assert "hello from test" in content
    assert "binggo.test" in content
    # 文件内容为 JSONL
    last = [line for line in content.splitlines() if line.strip()][-1]
    payload = json.loads(last)
    assert payload["msg"] == "hello from test"
    assert payload["logger"] == "binggo.test"
    reset_logging_for_tests()
