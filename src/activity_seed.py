"""内置活动种子：新用户首次启动时导入未结束活动，避免全量同步。"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from src.app_paths import CONFIG_DIR, ensure_user_dirs, install_root
from src.lottery_classifier import is_charging_lottery_activity
from src.lottery_time import resolve_effective_lottery_time_unix

BUNDLED_SEED_NAME = "activities_seed.json"
BUNDLED_SEED_PATH = install_root() / "config" / BUNDLED_SEED_NAME
USER_SEED_PATH = CONFIG_DIR / BUNDLED_SEED_NAME


def resolve_seed_path() -> Path | None:
    """优先用户 config 覆盖，其次安装包内置种子。"""
    if USER_SEED_PATH.is_file():
        return USER_SEED_PATH
    if BUNDLED_SEED_PATH.is_file():
        return BUNDLED_SEED_PATH
    return None


def is_activity_seedable(item: dict[str, Any], *, now: int | None = None) -> bool:
    if not item.get("dynamic_id"):
        return False
    if item.get("skipped") or is_charging_lottery_activity(item):
        return False
    if str(item.get("draw_status") or "") == "ended":
        return False
    if str(item.get("activity_status") or "") == "已结束":
        return False
    current = int(now if now is not None else time.time())
    effective_ts = resolve_effective_lottery_time_unix(item, None)
    return not (effective_ts and effective_ts <= current)


def sanitize_seed_activity(item: dict[str, Any]) -> dict[str, Any]:
    """去掉个人参与痕迹，新用户一律视为未参加。"""
    clean = dict(item)
    clean["activity_status"] = "未参加"
    clean["draw_status"] = "active"
    clean["draw_tag"] = ""
    clean.pop("platform_participated", None)
    if str(clean.get("lottery_type") or "") == "预约抽奖":
        clean["reserve_reserved"] = False
    else:
        clean.pop("reserve_reserved", None)
    return clean


def load_seed_payload(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("seed file must be a JSON object")
    return raw


def extract_seed_activities(payload: dict[str, Any], *, now: int | None = None) -> list[dict[str, Any]]:
    current = int(now if now is not None else time.time())
    activities: list[dict[str, Any]] = []
    for item in payload.get("activities") or []:
        if not isinstance(item, dict):
            continue
        if not is_activity_seedable(item, now=current):
            continue
        activities.append(sanitize_seed_activity(item))
    activities.sort(key=lambda row: str(row.get("dynamic_id")))
    return activities


def read_seed_activities(*, now: int | None = None) -> list[dict[str, Any]]:
    path = resolve_seed_path()
    if path is None:
        return []
    try:
        payload = load_seed_payload(path)
    except (OSError, json.JSONDecodeError, ValueError):
        return []
    return extract_seed_activities(payload, now=now)
