from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from src.user_data import participations_path
from src.user_data_lock import user_data_lock

ParticipationStatus = Literal["已参加", "未参加"]


@dataclass
class ParticipationRecord:
    dynamic_id: str
    user_status: ParticipationStatus
    updated_at: int
    source: Literal["participate"] = "participate"

    def to_dict(self) -> dict:
        return asdict(self)


def _load_raw() -> dict:
    path = participations_path()
    if not path.exists():
        return {"entries": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"entries": {}}
    data.setdefault("entries", {})
    return data


def _save_raw(data: dict) -> None:
    path = participations_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def load_participations() -> dict[str, ParticipationRecord]:
    entries = _load_raw().get("entries") or {}
    result: dict[str, ParticipationRecord] = {}
    for dynamic_id, item in entries.items():
        if not isinstance(item, dict):
            continue
        status = item.get("user_status")
        if status not in ("已参加", "未参加"):
            continue
        result[str(dynamic_id)] = ParticipationRecord(
            dynamic_id=str(dynamic_id),
            user_status=status,
            updated_at=int(item.get("updated_at") or 0),
        )
    return result


def set_participation(dynamic_id: str, user_status: ParticipationStatus) -> ParticipationRecord:
    with user_data_lock():
        data = _load_raw()
        record = ParticipationRecord(
            dynamic_id=dynamic_id,
            user_status=user_status,
            updated_at=int(time.time()),
        )
        data["entries"][dynamic_id] = record.to_dict()
        _save_raw(data)
        return record
