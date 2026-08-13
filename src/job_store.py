"""jobs 表短事务读写（方向三任务模型）。"""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import text
from sqlmodel import col, select

from src.db.json_cols import dumps_json, loads_json
from src.db.models import JobRow
from src.db.session import session_scope
from src.secrets_inventory import is_sanitize_secret_key

LOG_SUMMARY_MAX_BYTES = 16 * 1024
RESULT_JSON_MAX_BYTES = 64 * 1024
PARAM_VALUE_MAX_LEN = 500
HISTORY_RETENTION_SEC = 7 * 86400

_TERMINAL_STATES = frozenset({"success", "error", "cancelled", "interrupted"})


def truncate_log_summary(log: str, *, max_bytes: int = LOG_SUMMARY_MAX_BYTES) -> str:
    raw = (log or "").encode("utf-8")
    if len(raw) <= max_bytes:
        return log or ""
    marker = "…(truncated)\n".encode("utf-8")
    budget = max_bytes - len(marker)
    if budget <= 0:
        return "…(truncated)"
    tail = raw[-budget:]
    # 避免截断多字节字符
    while tail and (tail[0] & 0xC0) == 0x80:
        tail = tail[1:]
    return (marker + tail).decode("utf-8", errors="ignore")


def sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
    if not params:
        return {}
    out: dict[str, Any] = {}
    for key, value in params.items():
        key_s = str(key)
        if is_sanitize_secret_key(key_s):
            continue
        cleaned = _sanitize_param_value(value, depth=0)
        if cleaned is not None:
            out[key_s] = cleaned
    return out


def _sanitize_param_value(value: Any, *, depth: int) -> Any:
    if depth > 2:
        return {"_omitted": True}
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= PARAM_VALUE_MAX_LEN else value[:PARAM_VALUE_MAX_LEN] + "…"
    if isinstance(value, list):
        if depth >= 2:
            return {"_omitted": True}
        return [_sanitize_param_value(item, depth=depth + 1) for item in value[:50]]
    if isinstance(value, dict):
        nested: dict[str, Any] = {}
        for key, item in list(value.items())[:50]:
            key_s = str(key)
            if is_sanitize_secret_key(key_s):
                continue
            nested[key_s] = _sanitize_param_value(item, depth=depth + 1)
        return nested
    return str(value)[:PARAM_VALUE_MAX_LEN]


def dumps_result_json(result: dict[str, Any] | None) -> str | None:
    if result is None:
        return None
    if not isinstance(result, dict):
        return dumps_json({"_non_dict": True, "value": str(result)[:PARAM_VALUE_MAX_LEN]})
    text = dumps_json(result)
    raw = text.encode("utf-8")
    if len(raw) <= RESULT_JSON_MAX_BYTES:
        return text
    keep_keys = ("login_phase", "skipped", "joined", "failed", "from_auto", "qrcode_refreshed_at")
    slim: dict[str, Any] = {"_truncated": True, "keys": sorted(str(k) for k in result.keys())}
    for key in keep_keys:
        if key in result:
            slim[key] = result[key]
    return dumps_json(slim)


def row_to_dict(row: JobRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "action": row.action or "",
        "label": row.label or "",
        "state": row.state or "",
        "source": row.source or "ui",
        "account_uid": str(row.account_uid) if row.account_uid is not None else None,
        "params": loads_json(row.params_json, default={}) or {},
        "progress_step": int(row.progress_step or 0),
        "progress_total": int(row.progress_total or 0),
        "message": row.message or "",
        "log_summary": row.log_summary or "",
        "result": loads_json(row.result_json, default=None),
        "error_kind": row.error_kind,
        "created_at": row.created_at,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
    }


def insert_running_job(
    *,
    action: str,
    label: str,
    source: str,
    params: dict[str, Any] | None,
    account_uid: str | int | None = None,
    message: str = "任务已启动…",
    now: int | None = None,
) -> int:
    ts = int(now if now is not None else time.time())
    with session_scope() as session:
        row = JobRow(
            action=action,
            label=label,
            state="running",
            source=source or "ui",
            account_uid=str(account_uid) if account_uid is not None else None,
            params_json=dumps_json(sanitize_params(params)),
            progress_step=0,
            progress_total=0,
            message=message,
            log_summary="",
            result_json=None,
            error_kind=None,
            created_at=ts,
            started_at=ts,
            finished_at=None,
        )
        session.add(row)
        session.flush()
        if row.id is None:
            raise RuntimeError("插入 jobs 行失败：未获得 id")
        return int(row.id)


def update_job_progress(
    job_id: int,
    *,
    step: int,
    total: int,
    message: str,
    log_summary: str,
    result: dict[str, Any] | None = None,
) -> None:
    with session_scope() as session:
        row = session.get(JobRow, job_id)
        if row is None or row.state != "running":
            return
        row.progress_step = int(step)
        row.progress_total = int(total)
        row.message = message or ""
        row.log_summary = truncate_log_summary(log_summary)
        if result is not None:
            row.result_json = dumps_result_json(result)
        session.add(row)


def finish_job(
    job_id: int,
    *,
    state: str,
    message: str,
    log_summary: str,
    result: dict[str, Any] | None = None,
    error_kind: str | None = None,
    progress_step: int | None = None,
    progress_total: int | None = None,
    finished_at: int | None = None,
) -> bool:
    if state not in _TERMINAL_STATES:
        raise ValueError(f"非法终态: {state}")
    ts = int(finished_at if finished_at is not None else time.time())
    with session_scope() as session:
        row = session.get(JobRow, job_id)
        if row is None:
            return False
        if row.state != "running":
            # 已是目标终态则视为成功；其它终态不覆盖
            return row.state == state
        row.state = state
        row.message = message or ""
        row.log_summary = truncate_log_summary(log_summary)
        row.result_json = dumps_result_json(result)
        row.error_kind = error_kind
        row.finished_at = ts
        if progress_step is not None:
            row.progress_step = int(progress_step)
        if progress_total is not None:
            row.progress_total = int(progress_total)
        session.add(row)
        return True


def mark_interrupted_running(
    *,
    message: str = "进程退出，任务中断",
    now: int | None = None,
) -> int:
    ts = int(now if now is not None else time.time())
    with session_scope() as session:
        rows = session.exec(select(JobRow).where(JobRow.state == "running")).all()
        for row in rows:
            row.state = "interrupted"
            row.message = message
            row.error_kind = "interrupted"
            row.finished_at = ts
            session.add(row)
        return len(rows)


def prune_old_jobs(*, older_than_unix: int | None = None, now: int | None = None) -> int:
    """按 7 天策略删除终态历史；使用 SQL 条件，避免全表加载。"""
    ts_now = int(now if now is not None else time.time())
    cutoff = int(
        older_than_unix if older_than_unix is not None else ts_now - HISTORY_RETENTION_SEC
    )
    with session_scope() as session:
        result = session.execute(
            text(
                "DELETE FROM jobs "
                "WHERE state != 'running' "
                "AND COALESCE(finished_at, created_at, 0) < :cutoff"
            ),
            {"cutoff": cutoff},
        )
        return int(result.rowcount or 0)


def get_job(job_id: int) -> dict[str, Any] | None:
    with session_scope() as session:
        row = session.get(JobRow, job_id)
        if row is None:
            return None
        return row_to_dict(row)


def get_latest_job() -> dict[str, Any] | None:
    with session_scope() as session:
        row = session.exec(select(JobRow).order_by(col(JobRow.id).desc()).limit(1)).first()
        if row is None:
            return None
        return row_to_dict(row)


def list_recent_jobs(limit: int = 10) -> list[dict[str, Any]]:
    """按 id 降序，供 diagnostics；不是对外历史 API。"""
    capped = max(1, min(int(limit), 50))
    with session_scope() as session:
        rows = session.exec(select(JobRow).order_by(col(JobRow.id).desc()).limit(capped)).all()
        return [row_to_dict(row) for row in rows]
