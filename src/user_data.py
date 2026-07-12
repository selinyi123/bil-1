from __future__ import annotations

import shutil
from pathlib import Path

from src.bilibili_auth import get_login_uid
from src.state_store import DATA_DIR

USERS_DIR = DATA_DIR / "users"
LEGACY_PARTICIPATIONS = DATA_DIR / "participations.json"
LEGACY_ACTIONS = DATA_DIR / "participation_actions.json"


def get_active_uid() -> int | None:
    return get_login_uid()


def user_dir(uid: int) -> Path:
    return USERS_DIR / str(uid)


def participations_path() -> Path:
    uid = get_active_uid()
    if not uid:
        return LEGACY_PARTICIPATIONS
    path = user_dir(uid) / "participations.json"
    _migrate_legacy_file(LEGACY_PARTICIPATIONS, path)
    return path


def participation_actions_path() -> Path:
    uid = get_active_uid()
    if not uid:
        return LEGACY_ACTIONS
    path = user_dir(uid) / "participation_actions.json"
    _migrate_legacy_file(LEGACY_ACTIONS, path)
    return path


def _migrate_legacy_file(legacy_path: Path, user_path: Path) -> None:
    if user_path.exists() or not legacy_path.exists():
        return
    user_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(legacy_path, user_path)
