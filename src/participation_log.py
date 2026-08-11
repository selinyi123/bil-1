from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any, Literal

from sqlmodel import col, select

from src.db.json_cols import dumps_json, loads_json
from src.db.models import ParticipationActionRow
from src.db.session import session_scope
from src.db.uids import participation_uid
from src.lottery_actions import ActionResult
from src.user_data_lock import user_data_lock

ParticipationOutcome = Literal["joined", "failed", "skipped", "dry_run"]
CORE_ACTIONS = ("like", "follow", "favorite", "repost", "comment")
INTERACT_REQUIRED_ACTIONS = ("like", "follow", "favorite", "repost")
RESERVE_REQUIRED_ACTIONS = ("follow", "reserve")
COMMENT_OPTIONAL_ERROR_CODES = {12078}
_MAX_ENTRIES_PER_UID = 500


@dataclass
class ParticipationActionRecord:
    recorded_at: int
    dynamic_id: str
    lottery_type: str
    status: ParticipationOutcome
    message: str
    action_text: str
    actions: list[dict]
    context_snapshot: dict[str, Any]

    def to_dict(self) -> dict:
        return asdict(self)


def serialize_actions(actions: list[ActionResult]) -> list[dict]:
    return [
        {
            "action": item.action,
            "ok": item.ok,
            "detail": item.detail,
            **({"extra": item.extra} if item.extra else {}),
        }
        for item in actions
    ]


def load_action_entries_for_uid(uid: str | None = None) -> list[dict]:
    """供 activity_service 等读取当前用户动作日志。"""
    key = uid if uid is not None else participation_uid()
    with session_scope() as session:
        rows = session.exec(
            select(ParticipationActionRow)
            .where(ParticipationActionRow.uid == key)
            .order_by(col(ParticipationActionRow.recorded_at).asc(), col(ParticipationActionRow.id).asc())
        ).all()
        entries: list[dict] = []
        for row in rows:
            entries.append(
                {
                    "recorded_at": row.recorded_at,
                    "dynamic_id": row.dynamic_id,
                    "lottery_type": row.lottery_type,
                    "status": row.status,
                    "message": row.message,
                    "action_text": row.action_text,
                    "actions": loads_json(row.actions_json, default=[]),
                    "context_snapshot": loads_json(row.context_snapshot_json, default={}),
                }
            )
        return entries


def append_action_record_unlocked(record: ParticipationActionRecord) -> None:
    uid = participation_uid()
    with session_scope() as session:
        session.add(
            ParticipationActionRow(
                uid=uid,
                recorded_at=int(record.recorded_at),
                dynamic_id=str(record.dynamic_id or ""),
                lottery_type=str(record.lottery_type or ""),
                status=str(record.status or ""),
                message=str(record.message or ""),
                action_text=str(record.action_text or ""),
                actions_json=dumps_json(record.actions or []),
                context_snapshot_json=dumps_json(record.context_snapshot or {}),
            )
        )
        session.flush()
        rows = session.exec(
            select(ParticipationActionRow)
            .where(ParticipationActionRow.uid == uid)
            .order_by(col(ParticipationActionRow.recorded_at).desc(), col(ParticipationActionRow.id).desc())
        ).all()
        for stale in rows[_MAX_ENTRIES_PER_UID:]:
            session.delete(stale)


def append_action_record(record: ParticipationActionRecord) -> None:
    with user_data_lock():
        append_action_record_unlocked(record)


def _comment_failure_optional(action: ActionResult) -> bool:
    if action.action != "comment" or action.ok:
        return False
    detail = action.detail or ""
    if any(token in detail for token in ("关注UP主", "关注 up", "7天", "7 天")):
        return True
    for code in COMMENT_OPTIONAL_ERROR_CODES:
        if f"code={code}" in detail:
            return True
    return False


def participation_succeeded(actions: list[ActionResult], *, lottery_type: str) -> bool:
    action_map = {item.action: item for item in actions}
    if lottery_type == "预约抽奖":
        for name in RESERVE_REQUIRED_ACTIONS:
            item = action_map.get(name)
            if not item or not item.ok:
                return False
        return True
    if lottery_type == "互动抽奖":
        required = INTERACT_REQUIRED_ACTIONS
    else:
        required = CORE_ACTIONS
    for name in required:
        item = action_map.get(name)
        if not item or not item.ok:
            return False
    if lottery_type == "互动抽奖":
        comment = action_map.get("comment")
        if comment and not comment.ok and not _comment_failure_optional(comment):
            return False
    return True


def all_core_actions_ok(actions: list[ActionResult]) -> bool:
    action_map = {item.action: item.ok for item in actions}
    return all(action_map.get(name) for name in CORE_ACTIONS)
