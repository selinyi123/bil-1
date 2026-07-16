from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from src.lottery_classifier import is_charging_lottery_activity
from src.lottery_time import resolve_effective_lottery_time_unix
from src.sources.common import load_previous_output, normalize_activity_id
from src.state_store import DATA_DIR

ACTIVITIES_OUTPUT_PATH = DATA_DIR / "output" / "activities_latest.json"
LEGACY_ENRICHED_PATH = DATA_DIR / "output" / "enriched_latest.json"
_activity_lock = threading.RLock()


def _empty_payload() -> dict[str, Any]:
    return {
        "updated_at": 0,
        "activities": [],
        "counts": {"active": 0, "ended": 0},
        "user_status_counts": {"已结束": 0, "已参加": 0, "未参加": 0},
        "draw_tag_counts": {"即将开奖": 0},
    }


def _rebuild_counts(activities: list[dict]) -> dict[str, Any]:
    counts = {"active": 0, "ended": 0}
    user_status = {"已结束": 0, "已参加": 0, "未参加": 0}
    draw_tag_counts = {"即将开奖": 0}
    for item in activities:
        if is_charging_lottery_activity(item) or item.get("skipped"):
            continue
        if item.get("draw_status") == "ended":
            counts["ended"] += 1
        else:
            counts["active"] += 1
        status = str(item.get("activity_status") or "")
        if status in user_status:
            user_status[status] += 1
        tag = str(item.get("draw_tag") or "")
        if tag in draw_tag_counts:
            draw_tag_counts[tag] += 1
    return {
        "counts": counts,
        "user_status_counts": user_status,
        "draw_tag_counts": draw_tag_counts,
    }


def _normalize_ended_by_time(item: dict, *, now: int | None = None) -> bool:
    """已结束仅由开奖时间决定；清除历史「已开奖」标签。"""
    changed = False
    if str(item.get("draw_tag") or "") == "已开奖":
        item["draw_tag"] = ""
        changed = True
    current = int(now if now is not None else time.time())
    effective_ts = resolve_effective_lottery_time_unix(item, None)
    if effective_ts and effective_ts <= current:
        if str(item.get("activity_status") or "") != "已结束":
            item["activity_status"] = "已结束"
            changed = True
        if item.get("draw_status") != "ended":
            item["draw_status"] = "ended"
            changed = True
        if item.get("draw_tag"):
            item["draw_tag"] = ""
            changed = True
    return changed


def _migrate_legacy_if_needed() -> None:
    if ACTIVITIES_OUTPUT_PATH.exists():
        return
    legacy = load_previous_output(LEGACY_ENRICHED_PATH) or {}
    activities = [
        item
        for item in (legacy.get("activities") or [])
        if isinstance(item, dict)
        and not item.get("skipped")
        and not is_charging_lottery_activity(item)
        and item.get("dynamic_id")
    ]
    if not activities and not LEGACY_ENRICHED_PATH.exists():
        return
    payload = _empty_payload()
    payload["activities"] = sorted(activities, key=lambda x: str(x.get("dynamic_id")))
    payload["updated_at"] = int(legacy.get("enriched_at") or time.time())
    payload.update(_rebuild_counts(payload["activities"]))
    _write_payload(payload)


def _load_payload_unlocked() -> dict[str, Any]:
    _migrate_legacy_if_needed()
    if not ACTIVITIES_OUTPUT_PATH.exists():
        return _empty_payload()
    payload = load_previous_output(ACTIVITIES_OUTPUT_PATH) or _empty_payload()
    if "activities" not in payload:
        payload["activities"] = []
    activities = [item for item in (payload.get("activities") or []) if isinstance(item, dict)]
    changed = False
    for item in activities:
        if _normalize_ended_by_time(item):
            changed = True
    if changed:
        payload["activities"] = sorted(activities, key=lambda row: str(row.get("dynamic_id")))
        payload.update(_rebuild_counts(activities))
        payload["updated_at"] = int(time.time())
        _write_payload(payload)
    return payload


def load_payload() -> dict[str, Any]:
    with _activity_lock:
        return _load_payload_unlocked()


def load_activities() -> list[dict]:
    return [item for item in (load_payload().get("activities") or []) if isinstance(item, dict)]


def known_activity_ids() -> set[str]:
    ids: set[str] = set()
    for item in load_activities():
        dynamic_id = str(item.get("dynamic_id") or "").strip()
        if dynamic_id:
            ids.add(dynamic_id)
    return ids


def append_activities(new_items: list[dict]) -> int:
    if not new_items:
        return 0
    with _activity_lock:
        payload = _load_payload_unlocked()
        existing = {
            str(item.get("dynamic_id")): item
            for item in (payload.get("activities") or [])
            if isinstance(item, dict) and item.get("dynamic_id")
        }
        added = 0
        for item in new_items:
            dynamic_id = str(item.get("dynamic_id") or "").strip()
            if not dynamic_id or dynamic_id in existing:
                continue
            existing[dynamic_id] = item
            added += 1
        activities = sorted(existing.values(), key=lambda row: str(row.get("dynamic_id")))
        payload["activities"] = activities
        payload["updated_at"] = int(time.time())
        payload.update(_rebuild_counts(activities))
        _write_payload(payload)
        return added


def replace_all_activities(activities: list[dict]) -> None:
    with _activity_lock:
        payload = _empty_payload()
        payload["activities"] = sorted(activities, key=lambda row: str(row.get("dynamic_id")))
        payload["updated_at"] = int(time.time())
        payload.update(_rebuild_counts(payload["activities"]))
        _write_payload(payload)


def remove_activity_ids(dynamic_ids: set[str]) -> int:
    if not dynamic_ids:
        return 0
    with _activity_lock:
        payload = _load_payload_unlocked()
        before = len(payload.get("activities") or [])
        activities = [
            item
            for item in (payload.get("activities") or [])
            if isinstance(item, dict) and str(item.get("dynamic_id") or "") not in dynamic_ids
        ]
        removed = before - len(activities)
        if removed <= 0:
            return 0
        payload["activities"] = activities
        payload["updated_at"] = int(time.time())
        payload.update(_rebuild_counts(activities))
        _write_payload(payload)
        return removed


def update_activity(dynamic_id: str, item: dict) -> None:
    with _activity_lock:
        payload = _load_payload_unlocked()
        activities = [row for row in (payload.get("activities") or []) if isinstance(row, dict)]
        replaced = False
        for index, row in enumerate(activities):
            if str(row.get("dynamic_id") or "") == dynamic_id:
                activities[index] = item
                replaced = True
                break
        if not replaced:
            activities.append(item)
        payload["activities"] = sorted(activities, key=lambda row: str(row.get("dynamic_id")))
        payload["updated_at"] = int(time.time())
        payload.update(_rebuild_counts(payload["activities"]))
        _write_payload(payload)


def _write_payload(payload: dict[str, Any]) -> None:
    ACTIVITIES_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = ACTIVITIES_OUTPUT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(ACTIVITIES_OUTPUT_PATH)


def collect_urls_from_ids(dynamic_ids: set[str]) -> set[str]:
    return {normalize_activity_id(did) or did for did in dynamic_ids if did}
