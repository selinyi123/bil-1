"""uid 哨兵与解析（与落地规范一致）。"""

from __future__ import annotations

LEGACY_PARTICIPATION_UID = "__legacy__"
GLOBAL_SETTINGS_UID = "__global__"


def participation_uid() -> str:
    from src.user_data import get_active_uid

    uid = get_active_uid()
    return str(uid) if uid else LEGACY_PARTICIPATION_UID


def settings_uid() -> str:
    from src.user_data import get_active_uid

    uid = get_active_uid()
    return str(uid) if uid else GLOBAL_SETTINGS_UID
