"""从 binggo.log（JSONL）有界读取并按 job_id 过滤。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.app_logging import log_dir, log_file
from src.log_redact import redact_obj

DEFAULT_LIMIT = 200
MAX_LIMIT = 500
_MAX_READ_BYTES = 2 * 1024 * 1024  # 单文件最多读尾部 2MB，防爆内存


def clamp_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    value = int(limit)
    if value < 1 or value > MAX_LIMIT:
        raise ValueError(f"limit 须在 1～{MAX_LIMIT} 之间")
    return value


def iter_log_paths() -> list[Path]:
    """当前文件 + 最近一份备份（若存在）。"""
    current = log_file()
    paths: list[Path] = []
    if current.is_file():
        paths.append(current)
    backup = Path(str(current) + ".1")
    if backup.is_file():
        paths.append(backup)
    return paths


def _read_tail_text(path: Path, *, max_bytes: int = _MAX_READ_BYTES) -> str:
    size = path.stat().st_size
    with path.open("rb") as fh:
        if size > max_bytes:
            fh.seek(size - max_bytes)
            data = fh.read()
            # 丢弃可能被截断的第一行
            nl = data.find(b"\n")
            if nl >= 0:
                data = data[nl + 1 :]
        else:
            data = fh.read()
    return data.decode("utf-8", errors="replace")


def _parse_jsonl_lines(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def query_log_lines(
    *,
    job_id: int | None = None,
    limit: int | None = DEFAULT_LIMIT,
) -> dict[str, Any]:
    """返回正序（旧→新）的匹配行。"""
    capped = clamp_limit(limit)
    paths = iter_log_paths()
    # 先收集备份再当前，使整体偏旧→新；每文件内保持文件顺序
    collected: list[dict[str, Any]] = []
    # 扫描顺序：备份在前、当前在后
    ordered = list(reversed(paths)) if paths else []
    for path in ordered:
        try:
            text = _read_tail_text(path)
        except OSError:
            continue
        for row in _parse_jsonl_lines(text):
            if job_id is not None:
                row_id = row.get("job_id")
                try:
                    if row_id is None or int(row_id) != int(job_id):
                        continue
                except (TypeError, ValueError):
                    continue
            # 读侧再脱敏：兼容升级前明文行与漏网字段
            redacted = redact_obj(row)
            if isinstance(redacted, dict):
                collected.append(redacted)

    if len(collected) > capped:
        collected = collected[-capped:]

    return {
        "files": [p.name for p in paths],
        "count": len(collected),
        "lines": collected,
        "log_dir": str(log_dir()),
    }
