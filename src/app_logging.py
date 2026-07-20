"""应用日志：文件 JSONL（脱敏）+ 可选控制台人话格式。"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from src.app_paths import DATA_DIR
from src.log_context import get_context_fields
from src.log_redact import redact_obj, redact_text

# 与 src.log_span.BINGGO_FIELDS_KEY 保持一致（避免循环 import）
_BINGGO_FIELDS_KEY = "binggo_fields"

_LOGGER_NAME = "binggo"
_CONFIGURED = False
_LOG_FILENAME = "binggo.log"

DEFAULT_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
JSONL_VERSION = 1


def log_dir() -> Path:
    return Path(DATA_DIR) / "logs"


def log_file() -> Path:
    return log_dir() / _LOG_FILENAME


# 兼容旧 `from src.app_logging import LOG_DIR, LOG_FILE`；setup 后会刷新
LOG_DIR = log_dir()
LOG_FILE = log_file()


class ContextFieldsFilter(logging.Filter):
    """把 contextvars 与调用方 binggo_fields 挂到 LogRecord。"""

    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in get_context_fields().items():
            setattr(record, key, value)
        return True


def _record_binggo_fields(record: logging.LogRecord) -> dict[str, Any]:
    raw = getattr(record, _BINGGO_FIELDS_KEY, None)
    if isinstance(raw, dict):
        return raw
    return {}


class JsonLineFormatter(logging.Formatter):
    """每行一个 JSON 对象（UTF-8）。"""

    def format(self, record: logging.LogRecord) -> str:
        try:
            payload = self._build_payload(record)
            return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            fallback = {
                "v": JSONL_VERSION,
                "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "level": "ERROR",
                "logger": getattr(record, "name", "binggo"),
                "msg": "formatter_error",
            }
            return json.dumps(fallback, ensure_ascii=False, separators=(",", ":"))

    def _build_payload(self, record: logging.LogRecord) -> dict[str, Any]:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds")
        if ts.endswith("+00:00"):
            ts = ts[:-6] + "Z"
        msg = redact_text(record.getMessage())
        payload: dict[str, Any] = {
            "v": JSONL_VERSION,
            "ts": ts,
            "level": record.levelname,
            "logger": record.name,
            "msg": msg,
        }
        for key in ("job_id", "action", "job_source"):
            value = getattr(record, key, None)
            if value is not None and value != "":
                payload[key] = value

        fields = _record_binggo_fields(record)
        for key in ("event", "component", "source_id", "phase", "duration_ms", "error_kind"):
            if key in fields and fields[key] is not None and fields[key] != "":
                payload[key] = fields[key]
        extra = fields.get("extra")
        if isinstance(extra, dict) and extra:
            payload["extra"] = redact_obj(extra)

        # logger.exception / error(..., exc_info=True) 需写入堆栈，否则 JSONL 丢诊断信息
        exc_text: str | None = None
        if record.exc_info:
            try:
                exc_text = self.formatException(record.exc_info)
            except Exception:
                exc_text = "exc_format_error"
        elif getattr(record, "exc_text", None):
            exc_text = str(record.exc_text)
        if exc_text:
            if len(exc_text) > 4000:
                exc_text = exc_text[:4000] + "…"
            payload["exc"] = redact_text(exc_text)
        return payload


class ConsoleFormatter(logging.Formatter):
    """开发控制台人话格式，附带 job_id（若有）。"""

    def __init__(self) -> None:
        super().__init__(DEFAULT_FORMAT, datefmt=DATE_FORMAT)

    def format(self, record: logging.LogRecord) -> str:
        # 不改 record.msg，避免与 args/% 格式化竞态
        try:
            text = super().format(record)
        except Exception:
            text = f"{record.levelname} {record.name}: {record.getMessage()}"
        job_id = getattr(record, "job_id", None)
        if job_id is not None:
            # 插到 "NAME: " 之后，保持时间/级别前缀可读
            marker = f"{record.name}: "
            idx = text.find(marker)
            if idx >= 0:
                insert_at = idx + len(marker)
                text = f"{text[:insert_at]}[job={job_id}] {text[insert_at:]}"
            else:
                text = f"[job={job_id}] {text}"
        return redact_text(text)


def setup_logging(*, level: int = logging.INFO, console: bool = True) -> Path:
    """初始化应用日志：写入 data/logs/binggo.log（JSONL），可选同步输出到控制台。"""
    global _CONFIGURED, LOG_DIR, LOG_FILE
    directory = log_dir()
    path = log_file()
    LOG_DIR = directory
    LOG_FILE = path
    directory.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger(_LOGGER_NAME)
    root.setLevel(level)
    if _CONFIGURED:
        return path

    # Filter 只挂 handler，避免 logger+handler 双跑
    context_filter = ContextFieldsFilter()

    file_handler = RotatingFileHandler(
        path,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(JsonLineFormatter())
    file_handler.addFilter(context_filter)
    root.addHandler(file_handler)

    if console:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(ConsoleFormatter())
        stream_handler.addFilter(context_filter)
        root.addHandler(stream_handler)

    _CONFIGURED = True
    root.info("日志系统已初始化 → %s", path)
    return path


def reset_logging_for_tests() -> None:
    """测试专用：移除 handler 并允许重新 setup_logging。"""
    global _CONFIGURED
    root = logging.getLogger(_LOGGER_NAME)
    for handler in list(root.handlers):
        root.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass
    root.filters.clear()
    _CONFIGURED = False


def get_logger(name: str) -> logging.Logger:
    """获取子模块 logger，例如 get_logger('fetch') → binggo.fetch。"""
    if not _CONFIGURED:
        setup_logging(console=False)
    if name.startswith(f"{_LOGGER_NAME}."):
        return logging.getLogger(name)
    return logging.getLogger(f"{_LOGGER_NAME}.{name}")
