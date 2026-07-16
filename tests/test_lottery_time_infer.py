from __future__ import annotations

from pathlib import Path

from src.lottery_time import SIX_MONTHS_SECONDS, resolve_effective_lottery_time_unix
from src.participation_store import ParticipationRecord


def test_resolve_effective_lottery_time_uses_participation(tmp_path: Path) -> None:
    participate_at = 1_600_000_000
    item = {"dynamic_id": "1", "enriched_at": participate_at, "conditions": {}}
    participation = ParticipationRecord(
        dynamic_id="1",
        user_status="已参加",
        updated_at=participate_at,
    )
    inferred = resolve_effective_lottery_time_unix(item, participation, persist=True)
    assert inferred == participate_at + SIX_MONTHS_SECONDS
    assert item["lottery_time_inferred"] is True
