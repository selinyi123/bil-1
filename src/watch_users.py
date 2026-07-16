from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from src.bilibili_client import BilibiliClient
from src.watch_user_profile import resolve_watch_user_name

from src.app_paths import WATCH_CANDIDATES_PATH as CANDIDATES_PATH, WATCH_USERS_PATH, ensure_user_dirs
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


def _read_unlocked() -> dict[str, Any]:
    if not WATCH_USERS_PATH.exists():
        return {"users": [], "updated_at": 0}
    try:
        payload = json.loads(WATCH_USERS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"users": [], "updated_at": 0}
    if not isinstance(payload, dict):
        return {"users": [], "updated_at": 0}
    payload.setdefault("users", [])
    return payload


def _write_unlocked(payload: dict[str, Any]) -> None:
    WATCH_USERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = WATCH_USERS_PATH.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(WATCH_USERS_PATH)


def seed_from_candidates_if_empty() -> bool:
    """若 watch_users.json 不存在或为空，从 candidates 导入首批用户。"""
    with _watch_lock:
        payload = _read_unlocked()
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
        payload = {
            "seeded_from": str(CANDIDATES_PATH.name),
            "updated_at": int(time.time()),
            "users": imported,
        }
        _write_unlocked(payload)
        return True


def list_watch_users(*, ensure_seeded: bool = True) -> list[WatchUser]:
    if ensure_seeded:
        seed_from_candidates_if_empty()
    with _watch_lock:
        payload = _read_unlocked()
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
    if ensure_seeded:
        seed_from_candidates_if_empty()
    with _watch_lock:
        payload = _read_unlocked()
    users = list_watch_users(ensure_seeded=False)
    return {
        "updated_at": int(payload.get("updated_at") or 0),
        "count": len(users),
        "users": [user.to_dict() for user in users],
    }


def add_watch_user(*, mid: int) -> WatchUser:
    if mid <= 0:
        raise ValueError("MID 无效")
    with BilibiliClient(timeout=20.0) as client:
        display_name = resolve_watch_user_name(client, mid)
    with _watch_lock:
        payload = _read_unlocked()
        users = payload.get("users") or []
        for item in users:
            if int(item.get("mid") or 0) == mid:
                raise ValueError(f"用户 {mid} 已在监控列表中")
        user = WatchUser(mid=mid, name=display_name)
        users.append(user.to_dict())
        payload["users"] = users
        payload["updated_at"] = int(time.time())
        _write_unlocked(payload)
        return user


def remove_watch_user(*, mid: int) -> bool:
    with _watch_lock:
        payload = _read_unlocked()
        users = payload.get("users") or []
        kept = [item for item in users if int(item.get("mid") or 0) != mid]
        if len(kept) == len(users):
            return False
        payload["users"] = kept
        payload["updated_at"] = int(time.time())
        _write_unlocked(payload)
        return True
