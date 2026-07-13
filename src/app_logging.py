from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src.state_store import DATA_DIR

LOG_DIR = DATA_DIR / "logs"
LOG_FILE = LOG_DIR / "binggo.log"
_LOGGER_NAME = "binggo"
_CONFIGURED = False

DEFAULT_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(*, level: int = logging.INFO, console: bool = True) -> Path:
    """初始化应用日志：写入 data/logs/binggo.log，可选同步输出到控制台。"""
    global _CONFIGURED
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger(_LOGGER_NAME)
    root.setLevel(level)
    if _CONFIGURED:
        return LOG_FILE

    formatter = logging.Formatter(DEFAULT_FORMAT, datefmt=DATE_FORMAT)

    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    if console:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)

    _CONFIGURED = True
    root.info("日志系统已初始化 → %s", LOG_FILE)
    return LOG_FILE


def get_logger(name: str) -> logging.Logger:
    """获取子模块 logger，例如 get_logger('fetch') → binggo.fetch。"""
    if not _CONFIGURED:
        setup_logging(console=False)
    if name.startswith(f"{_LOGGER_NAME}."):
        return logging.getLogger(name)
    return logging.getLogger(f"{_LOGGER_NAME}.{name}")
