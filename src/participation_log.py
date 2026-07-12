from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from typing import Any, Literal

from src.lottery_actions import ActionResult
from src.user_data import participation_actions_path

ParticipationOutcome = Literal["joined", "failed", "skipped", "dry_run"]
CORE_ACTIONS = ("like", "follow", "favorite", "repost", "comment")


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


def all_core_actions_ok(actions: list[ActionResult]) -> bool:
    action_map = {item.action: item.ok for item in actions}
    return all(action_map.get(name) for name in CORE_ACTIONS)


def append_action_record(record: ParticipationActionRecord) -> None:
    data = _load_raw()
    entries = data.get("entries") or []
    if not isinstance(entries, list):
        entries = []
    entries.append(record.to_dict())
    data["entries"] = entries[-500:]
    data["updated_at"] = int(time.time())
    _save_raw(data)
