"""数据源 / 监控同步快照读写。"""

from __future__ import annotations

import time
from typing import Any

from sqlmodel import select

from src.db.json_cols import dumps_json, loads_json
from src.db.models import DsCheckSnapshotRow, WatchSyncSnapshotRow
from src.db.session import session_scope
from src.source_outputs import SOURCE_OUTPUTS

# 从数据源登记表派生，不手写：手写的那版漏了 ds8/ds9/ds10，于是它们走文件回退，
# 而 `save_result` 只写 DB 不写文件，回退恒定返回 None——两个源在「无变化」路径上
# 永远报「共 0 条链接」。派生之后，新增数据源不可能再漏登记。
FILENAME_TO_SOURCE: dict[str, str] = {
    path.name: source_id for source_id, path in SOURCE_OUTPUTS
}


def load_ds_check_dict(source_id: str) -> dict[str, Any] | None:
    with session_scope() as session:
        row = session.get(DsCheckSnapshotRow, source_id)
        if row is None:
            return None
        raw = loads_json(row.raw_json, default=None)
        if isinstance(raw, dict) and raw:
            return raw
        return {
            "source_id": row.source_id,
            "updated": bool(row.updated),
            "container_url": row.container_url or "",
            "container_id": row.container_id or "",
            "title": row.title or "",
            "published_at": row.published_at or 0,
            "previous_container_url": row.previous_container_url,
            "activity_links": loads_json(row.activity_links_json, default=[]),
            "checked_at": row.checked_at or 0,
            "link_hints": loads_json(row.link_hints_json, default={}),
            "cv_id": row.cv_id,
        }


def save_ds_check_dict(payload: dict[str, Any]) -> None:
    source_id = str(payload.get("source_id") or "").strip()
    if not source_id:
        raise ValueError("ds snapshot missing source_id")
    with session_scope() as session:
        row = session.get(DsCheckSnapshotRow, source_id)
        data = DsCheckSnapshotRow(
            source_id=source_id,
            updated=bool(payload.get("updated")),
            container_url=str(payload.get("container_url") or "") or None,
            container_id=str(payload.get("container_id") or "") or None,
            title=str(payload.get("title") or "") or None,
            published_at=int(payload["published_at"])
            if payload.get("published_at") is not None
            else None,
            previous_container_url=payload.get("previous_container_url"),
            checked_at=int(payload["checked_at"]) if payload.get("checked_at") is not None else None,
            cv_id=str(payload["cv_id"]) if payload.get("cv_id") is not None else None,
            activity_links_json=dumps_json(payload.get("activity_links") or []),
            link_hints_json=dumps_json(payload.get("link_hints") or {}),
            raw_json=dumps_json(payload),
        )
        if row is None:
            session.add(data)
        else:
            for field in (
                "updated",
                "container_url",
                "container_id",
                "title",
                "published_at",
                "previous_container_url",
                "checked_at",
                "cv_id",
                "activity_links_json",
                "link_hints_json",
                "raw_json",
            ):
                setattr(row, field, getattr(data, field))


def load_watch_sync_dict() -> dict[str, Any] | None:
    with session_scope() as session:
        row = session.get(WatchSyncSnapshotRow, 1)
        if row is None:
            return None
        raw = loads_json(row.raw_json, default=None)
        if isinstance(raw, dict) and raw:
            return raw
        return {
            "source_id": row.source_id,
            "synced_at": row.synced_at,
            "window_start": row.window_start,
            "window_end": row.window_end,
            "checked_at": row.checked_at,
            "activity_links": loads_json(row.activity_links_json, default=[]),
            "link_count": row.link_count,
            "users_total": row.users_total,
            "users_ok": row.users_ok,
            # users_failed 列是 int（失败计数），无法还原失败明细；
            # 固定返回 list[dict] 结构与 raw_json 路径保持一致（缺失时回退空列表）。
            "users_failed": [],
            "user_results": loads_json(row.user_results_json, default=[]),
        }


def save_watch_sync_dict(payload: dict[str, Any]) -> None:
    with session_scope() as session:
        row = session.get(WatchSyncSnapshotRow, 1)
        data = WatchSyncSnapshotRow(
            id=1,
            source_id=str(payload.get("source_id") or "WATCH"),
            synced_at=int(payload.get("synced_at") or time.time()),
            window_start=int(payload["window_start"])
            if payload.get("window_start") is not None
            else None,
            window_end=int(payload["window_end"]) if payload.get("window_end") is not None else None,
            checked_at=int(payload["checked_at"]) if payload.get("checked_at") is not None else None,
            activity_links_json=dumps_json(payload.get("activity_links") or []),
            link_count=int(payload.get("link_count") or 0),
            users_total=int(payload.get("users_total") or 0),
            users_ok=int(payload.get("users_ok") or 0),
            users_failed=int(payload.get("users_failed") or 0)
            if not isinstance(payload.get("users_failed"), list)
            else len(payload.get("users_failed") or []),
            user_results_json=dumps_json(payload.get("user_results") or []),
            raw_json=dumps_json(payload),
        )
        # users_failed in WatchSyncResult is a list in some code paths — keep raw_json authoritative
        if isinstance(payload.get("users_failed"), list):
            data.users_failed = len(payload.get("users_failed") or [])
        if row is None:
            session.add(data)
        else:
            for field in (
                "source_id",
                "synced_at",
                "window_start",
                "window_end",
                "checked_at",
                "activity_links_json",
                "link_count",
                "users_total",
                "users_ok",
                "users_failed",
                "user_results_json",
                "raw_json",
            ):
                setattr(row, field, getattr(data, field))


def count_ds_snapshots() -> int:
    with session_scope() as session:
        return len(session.exec(select(DsCheckSnapshotRow)).all())
