from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from typing import Any, Literal

from src.lottery_actions import ActionResult
from src.user_data import participation_actions_path
from src.user_data_lock import user_data_lock

ParticipationOutcome = Literal["joined", "failed", "skipped", "dry_run"]
CORE_ACTIONS = ("like", "follow", "favorite", "repost", "comment")
INTERACT_REQUIRED_ACTIONS = ("like", "follow", "favorite", "repost")
COMMENT_OPTIONAL_ERROR_CODES = {12078}


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


def _load_raw() -> dict:
    path = participation_actions_path()
    if not path.exists():
        return {"updated_at": 0, "entries": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"updated_at": 0, "entries": []}
    data.setdefault("entries", [])
    return data


def _save_raw(data: dict) -> None:
    path = participation_actions_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def serialize_actions(actions: list[ActionResult]) -> list[dict]:
    return [{"action": item.action, "ok": item.ok, "detail": item.detail} for item in actions]


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
        reserve = action_map.get("reserve")
        return bool(reserve and reserve.ok)
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


def append_action_record(record: ParticipationActionRecord) -> None:
    with user_data_lock():
        data = _load_raw()
        entries = data.get("entries") or []
        if not isinstance(entries, list):
            entries = []
        entries.append(record.to_dict())
        data["entries"] = entries[-500:]
        data["updated_at"] = int(time.time())
        _save_raw(data)
