from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from src.activity_status import DrawStatus, resolve_activity_status
from src.activity_store import (
    activity_count,
    activity_exists,
    activity_file_lock,
    append_activities,
    load_activities,
    replace_all_activities,
    update_activity,
)
from src.draw_reminder import classify_participated_draw
from src.fetch_activity_info import ENRICHED_OUTPUT_PATH
from src.lottery_classifier import PARTICIPATABLE_TYPES, is_charging_lottery_activity
from src.lottery_time import infer_and_persist_lottery_time, lottery_time_unix
from src.participation_store import ParticipationRecord, load_participations

DrawTag = str  # "" | "即将开奖"
LOCAL_STATUSES = frozenset({"已参加", "未参加"})


def _is_refresh_candidate(item: dict) -> bool:
    if not isinstance(item, dict) or item.get("skipped"):
        return False
    if is_charging_lottery_activity(item):
        return False
    if item.get("lottery_type") not in PARTICIPATABLE_TYPES:
        return False
    if str(item.get("draw_status") or "") == "ended":
        return False
    if str(item.get("activity_status") or "") == "已结束":
        return False
    return True


def _classify_activity(
    item: dict,
    participation: ParticipationRecord | None,
    *,
    now: int,
) -> tuple[str, DrawTag, DrawStatus] | None:
    effective_ts = lottery_time_unix(item)
    if not effective_ts:
        return None

    draw_status: DrawStatus = "ended" if effective_ts <= now else "active"
    base_status, _ = resolve_activity_status(
        draw_status="active",
        lottery_type=item.get("lottery_type"),
        platform_participated=item.get("platform_participated"),
        reserve_reserved=item.get("reserve_reserved"),
        conditions=item.get("conditions") or {},
        participation=participation,
    )
    if base_status not in LOCAL_STATUSES:
        return None

    if draw_status == "ended":
        return "已结束", "", draw_status

    activity_status = base_status
    draw_tag: DrawTag = ""
    if activity_status == "已参加":
        phase = classify_participated_draw(item, participation, now=now)
        if phase == "soon":
            draw_tag = "即将开奖"

    return activity_status, draw_tag, draw_status


def _apply_classification(
    item: dict,
    participation: ParticipationRecord | None,
    *,
    now: int,
) -> tuple[bool, bool, bool, bool]:
    """返回 (是否处理, 是否有字段变更, 是否新标记结束, 是否标记即将开奖)。"""
    classified = _classify_activity(item, participation, now=now)
    if classified is None:
        return False, False, False, False

    activity_status, draw_tag, draw_status = classified
    prev_status = str(item.get("activity_status") or "")
    prev_draw = str(item.get("draw_status") or "")
    prev_draw_tag = str(item.get("draw_tag") or "")
    ended_newly = draw_status == "ended" and prev_draw != "ended"
    soon_newly = draw_tag == "即将开奖" and prev_draw_tag != "即将开奖"

    item["draw_status"] = draw_status
    item["activity_status"] = activity_status
    item["draw_tag"] = draw_tag
    item["status_classified"] = True

    changed = (
        activity_status != prev_status
        or draw_status != prev_draw
        or draw_tag != prev_draw_tag
    )
    return True, changed, ended_newly, soon_newly


def _empty_result(*, total: int = 0) -> dict[str, Any]:
    return {
        "skipped": True,
        "scanned": 0,
        "updated": 0,
        "ended_marked": 0,
        "soon_marked": 0,
        "total": total,
    }


def persist_activity_record(
    item: dict,
    *,
    participation: ParticipationRecord | None = None,
    path: Path | None = None,
    now: int | None = None,
) -> dict:
    """参与前检查通过后，写回单条活动状态。"""
    _ = path  # 兼容旧调用签名；活动库已迁至 SQLite
    with activity_file_lock():
        if activity_count() == 0:
            raise RuntimeError("未找到活动库，请先执行一键更新")

        dynamic_id = str(item.get("dynamic_id") or "")
        current = int(now if now is not None else time.time())

        was_handled, _, _, _ = _apply_classification(item, participation, now=current)
        if not was_handled:
            raise RuntimeError("该活动不参与状态管理")

        if activity_exists(dynamic_id):
            update_activity(dynamic_id, item)
        else:
            append_activities([item])
        return item


def refresh_local_activity_statuses(*, path: Path | None = None) -> dict[str, Any]:
    """刷新全库未结束活动：按开奖时间标记已结束 / 即将开奖。"""
    _ = path
    with activity_file_lock():
        activities = load_activities()
        if not activities:
            return _empty_result()

        participations = load_participations()
        now = int(time.time())

        scanned = 0
        updated = 0
        ended_marked = 0
        soon_marked = 0

        for item in activities:
            if not _is_refresh_candidate(item):
                continue

            dynamic_id = str(item.get("dynamic_id") or "")
            was_handled, changed, ended_newly, soon_newly = _apply_classification(
                item,
                participations.get(dynamic_id),
                now=now,
            )
            if not was_handled:
                continue

            scanned += 1
            if changed:
                updated += 1
            if ended_newly:
                ended_marked += 1
            if soon_newly:
                soon_marked += 1

        replace_all_activities(activities)

        return {
            "skipped": scanned == 0,
            "scanned": scanned,
            "updated": updated,
            "ended_marked": ended_marked,
            "soon_marked": soon_marked,
            "total": len(activities),
        }


def backfill_missing_lottery_times(*, path: Path | None = None) -> dict[str, Any]:
    """为本地缺失开奖时间的活动补全推断时间（参奖后半年）。"""
    _ = path
    with activity_file_lock():
        activities = load_activities()
        if not activities:
            return {"updated": 0, "total": 0}

        participations = load_participations()
        updated = 0

        for item in activities:
            if is_charging_lottery_activity(item):
                continue
            if item.get("lottery_type") not in PARTICIPATABLE_TYPES:
                continue
            if infer_and_persist_lottery_time(item, participations.get(str(item.get("dynamic_id") or ""))):
                updated += 1

        if updated:
            replace_all_activities(activities)

        return {"updated": updated, "total": len(activities)}
