from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from typing import Any

from sqlmodel import select

from src.app_paths import WATCH_CANDIDATES_PATH as CANDIDATES_PATH, WATCH_USERS_PATH, ensure_user_dirs
from src.bilibili_client import BilibiliClient
from src.db.models import WatchUserRow, WatchUsersMetaRow
from src.db.session import session_scope
from src.watch_user_profile import resolve_watch_user_name

_watch_lock = threading.Lock()


@dataclass
class WatchUser:
    mid: int
    name: str

    def to_dict(self) -> dict[str, Any]:
        return {"mid": self.mid, "name": self.name}


def _normalize_user(raw: dict[str, Any]) -> WatchUser | None:
    try:
        mid = int(raw.get("mid") or 0)
    except (TypeError, ValueError):
        return None
    if mid <= 0:
        return None
    name = str(raw.get("name") or mid).strip() or str(mid)
    return WatchUser(mid=mid, name=name)


def _read_payload() -> dict[str, Any]:
    with session_scope() as session:
        meta = session.get(WatchUsersMetaRow, 1)
        users = []
        for row in session.exec(select(WatchUserRow).order_by(WatchUserRow.mid)).all():
            users.append({"mid": row.mid, "name": row.name})
        return {
            "users": users,
            "updated_at": int(meta.updated_at) if meta else 0,
            "seeded_from": meta.seeded_from if meta else None,
        }


def _write_payload(payload: dict[str, Any]) -> None:
    users_raw = payload.get("users") or []
    updated_at = int(payload.get("updated_at") or time.time())
    seeded_from = payload.get("seeded_from")
    with session_scope() as session:
        for row in session.exec(select(WatchUserRow)).all():
            session.delete(row)
        session.flush()
        for item in users_raw:
            if not isinstance(item, dict):
                continue
            user = _normalize_user(item)
            if user is None:
                continue
            session.add(WatchUserRow(mid=user.mid, name=user.name, updated_at=updated_at))
        meta = session.get(WatchUsersMetaRow, 1)
        if meta is None:
            session.add(
                WatchUsersMetaRow(
                    id=1,
                    updated_at=updated_at,
                    seeded_from=str(seeded_from) if seeded_from else None,
                )
            )
        else:
            meta.updated_at = updated_at
            meta.seeded_from = str(seeded_from) if seeded_from else None


def seed_from_candidates_if_empty() -> bool:
    with _watch_lock:
        payload = _read_payload()
        users = payload.get("users") or []
        if users:
            return False
        if not CANDIDATES_PATH.exists():
            return False
        try:
            candidates = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return False
        imported: list[dict[str, Any]] = []
        seen: set[int] = set()
        for item in candidates.get("users") or []:
            if not isinstance(item, dict):
                continue
            user = _normalize_user(item)
            if not user or user.mid in seen:
                continue
            seen.add(user.mid)
            imported.append(user.to_dict())
        if not imported:
            return False
        _write_payload(
            {
                "seeded_from": str(CANDIDATES_PATH.name),
                "updated_at": int(time.time()),
                "users": imported,
            }
        )
        return True


def list_watch_users(*, ensure_seeded: bool = True) -> list[WatchUser]:
    if ensure_seeded:
        seed_from_candidates_if_empty()
    with _watch_lock:
        payload = _read_payload()
    users: list[WatchUser] = []
    seen: set[int] = set()
    for item in payload.get("users") or []:
        if not isinstance(item, dict):
            continue
        user = _normalize_user(item)
        if not user or user.mid in seen:
            continue
        seen.add(user.mid)
        users.append(user)
    return users


def get_watch_users_payload(*, ensure_seeded: bool = True) -> dict[str, Any]:
    users = list_watch_users(ensure_seeded=ensure_seeded)
    with _watch_lock:
        payload = _read_payload()
    return {
        "updated_at": int(payload.get("updated_at") or 0),
        "count": len(users),
        "users": [user.to_dict() for user in users],
    }


def add_watch_user(*, mid: int) -> WatchUser:
    ensure_user_dirs()
    mid_i = int(mid)
    if mid_i <= 0:
        raise ValueError("无效的 mid")
    with BilibiliClient() as client:
        name = resolve_watch_user_name(client, mid_i)
    user = WatchUser(mid=mid_i, name=name)
    with _watch_lock:
        payload = _read_payload()
        users = [item for item in (payload.get("users") or []) if isinstance(item, dict)]
        users = [item for item in users if int(item.get("mid") or 0) != mid_i]
        users.append(user.to_dict())
        payload["users"] = users
        payload["updated_at"] = int(time.time())
        _write_payload(payload)
    return user


def remove_watch_user(*, mid: int) -> bool:
    mid_i = int(mid)
    with _watch_lock:
        payload = _read_payload()
        users = [item for item in (payload.get("users") or []) if isinstance(item, dict)]
        before = len(users)
        users = [item for item in users if int(item.get("mid") or 0) != mid_i]
        if len(users) == before:
            return False
        payload["users"] = users
        payload["updated_at"] = int(time.time())
        _write_payload(payload)
        return True
