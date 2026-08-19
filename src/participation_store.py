from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Literal

from sqlmodel import select

from src.db.models import ParticipationRow
from src.db.session import session_scope
from src.db.uids import participation_uid
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


def load_participations_for_uid(uid: str | int) -> dict[str, ParticipationRecord]:
    uid = str(uid)
    with session_scope() as session:
        rows = session.exec(select(ParticipationRow).where(ParticipationRow.uid == uid)).all()
        result: dict[str, ParticipationRecord] = {}
        for row in rows:
            if row.user_status not in ("已参加", "未参加"):
                continue
            result[str(row.dynamic_id)] = ParticipationRecord(
                dynamic_id=str(row.dynamic_id),
                user_status=row.user_status,  # type: ignore[arg-type]
                updated_at=int(row.updated_at or 0),
                source="participate",
            )
        return result


def load_participations() -> dict[str, ParticipationRecord]:
    return load_participations_for_uid(participation_uid())


def set_participation_unlocked_for_uid(
    dynamic_id: str,
    user_status: ParticipationStatus,
    *,
    uid: str | int,
) -> ParticipationRecord:
    uid = str(uid)
    record = ParticipationRecord(
        dynamic_id=dynamic_id,
        user_status=user_status,
        updated_at=int(time.time()),
    )
    with session_scope() as session:
        row = session.get(ParticipationRow, (uid, dynamic_id))
        if row is None:
            session.add(
                ParticipationRow(
                    uid=uid,
                    dynamic_id=dynamic_id,
                    user_status=user_status,
                    updated_at=record.updated_at,
                    source="participate",
                )
            )
        else:
            row.user_status = user_status
            row.updated_at = record.updated_at
            row.source = "participate"
    return record


def set_participation_unlocked(dynamic_id: str, user_status: ParticipationStatus) -> ParticipationRecord:
    return set_participation_unlocked_for_uid(
        dynamic_id,
        user_status,
        uid=participation_uid(),
    )


def set_participation_for_uid(
    dynamic_id: str,
    user_status: ParticipationStatus,
    *,
    uid: str | int,
) -> ParticipationRecord:
    with user_data_lock():
        return set_participation_unlocked_for_uid(dynamic_id, user_status, uid=uid)


def set_participation(dynamic_id: str, user_status: ParticipationStatus) -> ParticipationRecord:
    return set_participation_for_uid(
        dynamic_id,
        user_status,
        uid=participation_uid(),
    )
