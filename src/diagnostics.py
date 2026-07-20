"""组装脱敏诊断包（无 FastAPI 依赖）。"""

from __future__ import annotations

import platform
from datetime import datetime, timezone
from typing import Any

from src import app_paths
from src.app_paths import runtime_label
from src.job_store import get_latest_job, list_recent_jobs, truncate_log_summary
from src.log_query import DEFAULT_LIMIT, query_log_lines
from src.log_redact import redact_obj, redact_text
from src.secrets_inventory import secret_filenames_csv


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _slim_job(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    log_summary = truncate_log_summary(str(row.get("log_summary") or ""), max_bytes=4 * 1024)
    slim = {
        "id": row.get("id"),
        "action": row.get("action"),
        "state": row.get("state"),
        "source": row.get("source"),
        "label": row.get("label"),
        "message": redact_text(str(row.get("message") or "")),
        "error_kind": row.get("error_kind"),
        "progress_step": row.get("progress_step"),
        "progress_total": row.get("progress_total"),
        "created_at": row.get("created_at"),
        "started_at": row.get("started_at"),
        "finished_at": row.get("finished_at"),
        "log_summary": redact_text(log_summary),
    }
    return slim


def _slim_auto_status(status: dict[str, Any] | None) -> dict[str, Any] | None:
    """对齐 AutoScheduler.get_status()/to_dict 字段。"""
    if not status:
        return None
    logs = status.get("logs")
    logs_tail: list[Any] = []
    if isinstance(logs, list) and logs:
        for item in logs[-5:]:
            logs_tail.append(redact_obj(item) if isinstance(item, (dict, list, str)) else item)
    return {
        "state": status.get("state"),
        "state_label": status.get("state_label"),
        "message": redact_text(str(status.get("message") or "")),
        "fatal_error": redact_text(str(status.get("fatal_error") or "")) or None,
        "current_phase": status.get("current_phase"),
        "next_hint": status.get("next_hint"),
        "next_slot": status.get("next_slot"),
        "server_now_unix": status.get("server_now_unix"),
        "job_probe": status.get("job_probe"),
        "logs_tail": logs_tail,
    }


def build_diagnostics_bundle(
    *,
    job_id: int | None = None,
    current_job: dict[str, Any] | None = None,
    auto_status: dict[str, Any] | None = None,
    log_limit: int = 300,
) -> dict[str, str]:
    """返回 {filename, text}，text 已脱敏。"""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"binggo-diagnostics-{stamp}.txt"

    schema_version: Any = None
    try:
        from src.db.schema import SCHEMA_VERSION

        schema_version = SCHEMA_VERSION
    except Exception:
        schema_version = None

    recent = [_slim_job(row) for row in list_recent_jobs(10)]
    latest = _slim_job(get_latest_job())
    current = _slim_job(current_job)

    try:
        capped = max(1, min(int(log_limit), 500))
        log_payload = query_log_lines(job_id=job_id, limit=capped)
    except ValueError:
        log_payload = query_log_lines(job_id=job_id, limit=DEFAULT_LIMIT)

    lines: list[str] = [
        "=== Binggo diagnostics ===",
        f"version: {app_paths.__version__}",
        f"runtime: {runtime_label()}",
        f"platform: {app_paths.platform_label()}",
        f"platform_os: {platform.platform()}",
        f"exported_at: {_iso_now()}",
        f"secrets_excluded: {secret_filenames_csv()}",
    ]
    if schema_version is not None:
        lines.append(f"schema_version: {schema_version}")
    if job_id is not None:
        lines.append(f"filter_job_id: {job_id}")

    lines.append("")
    lines.append("=== jobs (current) ===")
    lines.append(str(current or latest or {}))
    lines.append("")
    lines.append("=== jobs (recent) ===")
    for row in recent:
        lines.append(str(row))

    lines.append("")
    lines.append("=== auto ===")
    lines.append(str(_slim_auto_status(auto_status) or {}))

    lines.append("")
    lines.append(f"=== logs (files={log_payload.get('files')}, count={log_payload.get('count')}) ===")
    for row in log_payload.get("lines") or []:
        lines.append(str(row))

    text = redact_text("\n".join(lines) + "\n")
    return {"filename": filename, "text": text}
