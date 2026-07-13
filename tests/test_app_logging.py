from __future__ import annotations

import logging
from pathlib import Path

from src.app_logging import get_logger, setup_logging


def test_setup_logging_creates_file(tmp_path, monkeypatch) -> None:
    log_dir = tmp_path / "logs"
    monkeypatch.setattr("src.app_logging.LOG_DIR", log_dir)
    monkeypatch.setattr("src.app_logging.LOG_FILE", log_dir / "binggo.log")
    monkeypatch.setattr("src.app_logging._CONFIGURED", False)

    path = setup_logging(console=False)
    assert path == log_dir / "binggo.log"
    assert path.exists()

    child = get_logger("test")
    child.info("hello from test")
    content = path.read_text(encoding="utf-8")
    assert "hello from test" in content
    assert "binggo.test" in content
