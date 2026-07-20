from __future__ import annotations

import threading
import time
from typing import Any

from sqlmodel import select

from src.app_paths import DATA_DIR, ensure_user_dirs
from src.db.models import PipelineMetaRow, SourceCheckpointRow, WatchMetaRow
from src.db.session import session_scope

STATE_PATH = DATA_DIR / "state.json"
_state_lock = threading.Lock()


def _seed_state_if_missing() -> bool:
    """仅在「从未写入过 state」时播种；对应旧逻辑「state.json 不存在才 seed」。

    若 sources 被清空但 watch_meta/pipeline_meta 已存在，视为已初始化，禁止再次播种，
    避免 load_state 覆盖用户写入的空检查点或 pipeline 统计。
    """
    with session_scope() as session:
        has_source = session.exec(select(SourceCheckpointRow).limit(1)).first() is not None
        has_watch = session.get(WatchMetaRow, 1) is not None
        has_pipeline = session.get(PipelineMetaRow, 1) is not None
        if has_source or has_watch or has_pipeline:
            return False
    from src.state_seed import read_seed_state

    payload = read_seed_state()
    sources = payload.get("sources") or {}
    if not sources:
        return False
    ensure_user_dirs()
    _write_state_dict(payload)
    return True


def seed_state_if_missing() -> bool:
    with _state_lock:
        return _seed_state_if_missing()


def _read_state_dict() -> dict[str, Any]:
    _seed_state_if_missing()
    with session_scope() as session:
        sources: dict[str, Any] = {}
        for row in session.exec(select(SourceCheckpointRow)).all():
            entry: dict[str, Any] = {
                "container_url": row.container_url,
                "container_id": row.container_id,
                "title": row.title,
                "checked_at": row.checked_at,
            }
            if row.cv_id is not None:
                entry["cv_id"] = row.cv_id
            sources[row.source_id] = entry
        watch_row = session.get(WatchMetaRow, 1)
        pipeline_row = session.get(PipelineMetaRow, 1)
        state: dict[str, Any] = {"sources": sources}
        if watch_row is not None and watch_row.last_synced_at is not None:
            state["watch"] = {"last_synced_at": watch_row.last_synced_at}
        if pipeline_row is not None:
            state["pipeline"] = {
                "last_action": pipeline_row.last_action,
                "last_persisted_count": pipeline_row.last_persisted_count,
                "last_synced_at": pipeline_row.last_synced_at,
            }
        return state


def _write_state_dict(state: dict[str, Any]) -> None:
    sources = state.get("sources") or {}
    watch = state.get("watch") or {}
    pipeline = state.get("pipeline") or {}
    with session_scope() as session:
        for row in session.exec(select(SourceCheckpointRow)).all():
            if row.source_id not in sources:
                session.delete(row)
        for source_id, raw in sources.items():
            if not isinstance(raw, dict):
                continue
            sid = str(source_id)
            entry = SourceCheckpointRow(
                source_id=sid,
                container_url=raw.get("container_url"),
                container_id=raw.get("container_id"),
                title=raw.get("title"),
                cv_id=raw.get("cv_id"),
                checked_at=int(raw["checked_at"]) if raw.get("checked_at") is not None else None,
            )
            existing = session.get(SourceCheckpointRow, sid)
            if existing is None:
                session.add(entry)
            else:
                existing.container_url = entry.container_url
                existing.container_id = entry.container_id
                existing.title = entry.title
                existing.cv_id = entry.cv_id
                existing.checked_at = entry.checked_at

        watch_row = session.get(WatchMetaRow, 1)
        last_synced = watch.get("last_synced_at")
        if watch_row is None:
            session.add(
                WatchMetaRow(
                    id=1,
                    last_synced_at=int(last_synced) if last_synced is not None else None,
                )
            )
        else:
            watch_row.last_synced_at = int(last_synced) if last_synced is not None else None

        pipe_row = session.get(PipelineMetaRow, 1)
        try:
            persisted = int(pipeline.get("last_persisted_count") or 0)
        except (TypeError, ValueError):
            persisted = 0
        synced_at = pipeline.get("last_synced_at")
        try:
            synced_at_i = int(synced_at) if synced_at is not None else None
        except (TypeError, ValueError):
            synced_at_i = None
        if pipe_row is None:
            session.add(
                PipelineMetaRow(
                    id=1,
                    last_action=str(pipeline.get("last_action") or "") or None,
                    last_persisted_count=max(0, persisted),
                    last_synced_at=synced_at_i,
                )
            )
        else:
            pipe_row.last_action = str(pipeline.get("last_action") or "") or None
            pipe_row.last_persisted_count = max(0, persisted)
            pipe_row.last_synced_at = synced_at_i


def load_state() -> dict:
    with _state_lock:
        return _read_state_dict()


def save_state(state: dict) -> None:
    with _state_lock:
        _write_state_dict(state)


def get_last_container(source_id: str) -> str | None:
    seed_state_if_missing()
    with session_scope() as session:
        row = session.get(SourceCheckpointRow, source_id)
        if row is None:
            return None
        return row.container_url


def get_last_cv_id(source_id: str) -> str | None:
    seed_state_if_missing()
    with session_scope() as session:
        row = session.get(SourceCheckpointRow, source_id)
        if row is None:
            return None
        return row.cv_id


def set_last_container(
    source_id: str,
    container_url: str,
    *,
    container_id: str | None = None,
    title: str | None = None,
    cv_id: str | None = None,
) -> None:
    with _state_lock:
        with session_scope() as session:
            entry = SourceCheckpointRow(
                source_id=source_id,
                container_url=container_url,
                container_id=container_id,
                title=title,
                checked_at=int(time.time()),
                cv_id=cv_id,
            )
            existing = session.get(SourceCheckpointRow, source_id)
            if existing is None:
                session.add(entry)
            else:
                existing.container_url = entry.container_url
                existing.container_id = entry.container_id
                existing.title = entry.title
                existing.checked_at = entry.checked_at
                if cv_id is not None:
                    existing.cv_id = cv_id


def get_watch_last_synced_at() -> int | None:
    seed_state_if_missing()
    with session_scope() as session:
        row = session.get(WatchMetaRow, 1)
        if row is None or row.last_synced_at is None:
            return None
        try:
            parsed = int(row.last_synced_at)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None


def set_watch_last_synced_at(timestamp: int) -> None:
    with _state_lock:
        with session_scope() as session:
            row = session.get(WatchMetaRow, 1)
            if row is None:
                session.add(WatchMetaRow(id=1, last_synced_at=int(timestamp)))
            else:
                row.last_synced_at = int(timestamp)


def set_last_pipeline_persisted(*, action: str, persisted_count: int, synced_at: int | None = None) -> None:
    with _state_lock:
        with session_scope() as session:
            row = session.get(PipelineMetaRow, 1)
            payload = PipelineMetaRow(
                id=1,
                last_action=str(action or "").strip() or None,
                last_persisted_count=max(0, int(persisted_count)),
                last_synced_at=int(synced_at if synced_at is not None else time.time()),
            )
            if row is None:
                session.add(payload)
            else:
                row.last_action = payload.last_action
                row.last_persisted_count = payload.last_persisted_count
                row.last_synced_at = payload.last_synced_at


def get_last_pipeline_persisted() -> dict:
    seed_state_if_missing()
    with session_scope() as session:
        row = session.get(PipelineMetaRow, 1)
        if row is None:
            return {"action": "", "persisted_count": 0, "synced_at": None}
        action = str(row.last_action or "").strip()
        try:
            persisted_count = int(row.last_persisted_count or 0)
        except (TypeError, ValueError):
            persisted_count = 0
        if persisted_count < 0:
            persisted_count = 0
        synced_at = row.last_synced_at
        try:
            synced_at_i = int(synced_at) if synced_at else None
        except (TypeError, ValueError):
            synced_at_i = None
        if synced_at_i is not None and synced_at_i <= 0:
            synced_at_i = None
        return {
            "action": action,
            "persisted_count": persisted_count,
            "synced_at": synced_at_i,
        }
