"""内置 state 种子：新用户首次启动时写入数据源检查点，避免一键更新误判全量爬取。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.app_paths import CONFIG_DIR, install_root

BUNDLED_STATE_SEED_NAME = "state_seed.json"
BUNDLED_STATE_SEED_PATH = install_root() / "config" / BUNDLED_STATE_SEED_NAME
USER_STATE_SEED_PATH = CONFIG_DIR / BUNDLED_STATE_SEED_NAME

REQUIRED_SOURCE_IDS = tuple(f"DS-{index}" for index in range(1, 7))


def resolve_state_seed_path() -> Path | None:
    if USER_STATE_SEED_PATH.is_file():
        return USER_STATE_SEED_PATH
    if BUNDLED_STATE_SEED_PATH.is_file():
        return BUNDLED_STATE_SEED_PATH
    return None


def sanitize_seed_state(payload: dict[str, Any]) -> dict[str, Any]:
    sources = payload.get("sources") or {}
    if not isinstance(sources, dict):
        sources = {}
    cleaned_sources: dict[str, Any] = {}
    for source_id in REQUIRED_SOURCE_IDS:
        entry = sources.get(source_id)
        if not isinstance(entry, dict):
            continue
        container_url = str(entry.get("container_url") or "").strip()
        if not container_url:
            continue
        cleaned: dict[str, Any] = {
            "container_url": container_url,
            "checked_at": int(entry.get("checked_at") or 0),
        }
        container_id = str(entry.get("container_id") or "").strip()
        if container_id:
            cleaned["container_id"] = container_id
        title = str(entry.get("title") or "").strip()
        if title:
            cleaned["title"] = title
        cv_id = str(entry.get("cv_id") or "").strip()
        if cv_id:
            cleaned["cv_id"] = cv_id
        cleaned_sources[source_id] = cleaned

    state: dict[str, Any] = {"sources": cleaned_sources}
    watch = payload.get("watch")
    if isinstance(watch, dict):
        last_synced = watch.get("last_synced_at")
        try:
            synced_at = int(last_synced)
        except (TypeError, ValueError):
            synced_at = 0
        if synced_at > 0:
            state["watch"] = {"last_synced_at": synced_at}
    return state


def load_state_seed_payload(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("state seed must be a JSON object")
    return sanitize_seed_state(raw)


def read_seed_state() -> dict[str, Any]:
    path = resolve_state_seed_path()
    if path is None:
        return {}
    try:
        return load_state_seed_payload(path)
    except (OSError, json.JSONDecodeError, ValueError):
        return {}
