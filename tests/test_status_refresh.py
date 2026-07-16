from __future__ import annotations

import json
from pathlib import Path

from src.participation_store import ParticipationRecord
from src.status_refresh import (
    backfill_missing_lottery_times,
    refresh_local_activity_statuses,
)


def _write_enriched(path: Path, *, activities: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "activities": activities,
                "total_count": len(activities),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _activity(
    dynamic_id: str,
    *,
    lottery_time: int | None = None,
    enriched_at: int = 1_600_000_000,
    platform_participated: bool = False,
    activity_status: str = "未参加",
    draw_status: str = "active",
    lottery_type: str = "互动抽奖",
) -> dict:
    payload = {
        "dynamic_id": dynamic_id,
        "lottery_type": lottery_type,
        "draw_status": draw_status,
        "enriched_at": enriched_at,
        "platform_participated": platform_participated,
        "activity_status": activity_status,
        "conditions": {},
        "prizes": [{"tier": "1", "winner_count": 1, "description": "奖品"}],
        "repost_fetched": True,
    }
    if lottery_time is not None:
        payload["lottery_time"] = lottery_time
    return payload


def test_local_refresh_skips_charging_and_ended(tmp_path: Path, monkeypatch) -> None:
    now = 1_700_000_000
    monkeypatch.setattr("src.status_refresh.time.time", lambda: now)

    path = tmp_path / "enriched_latest.json"
    charging = _activity("charge-1", lottery_type="充电抽奖", lottery_time=now - 10)
    charging["business_type"] = 12
    charging["skipped"] = True
    ended = _activity("ended-1", lottery_time=now - 10, draw_status="ended", activity_status="已结束")
    _write_enriched(path, activities=[charging, ended])

    result = refresh_local_activity_statuses(path=path)

    assert result["scanned"] == 0
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["activities"][0].get("status_classified") is not True


def test_local_refresh_marks_past_activity_ended(tmp_path: Path, monkeypatch) -> None:
    now = 1_700_000_000
    monkeypatch.setattr("src.status_refresh.time.time", lambda: now)

    path = tmp_path / "enriched_latest.json"
    item = _activity("past-1", lottery_time=now - 60, platform_participated=True)
    _write_enriched(path, activities=[item])

    result = refresh_local_activity_statuses(path=path)

    assert result["scanned"] == 1
    assert result["ended_marked"] == 1
    refreshed = json.loads(path.read_text(encoding="utf-8"))["activities"][0]
    assert refreshed["activity_status"] == "已结束"
    assert refreshed["draw_tag"] == ""


def test_local_refresh_skips_missing_lottery_time(tmp_path: Path, monkeypatch) -> None:
    now = 1_700_000_000
    monkeypatch.setattr("src.status_refresh.time.time", lambda: now)

    path = tmp_path / "enriched_latest.json"
    item = _activity("no-time-1", lottery_time=None)
    _write_enriched(path, activities=[item])

    result = refresh_local_activity_statuses(path=path)

    assert result["scanned"] == 0
    refreshed = json.loads(path.read_text(encoding="utf-8"))["activities"][0]
    assert refreshed.get("lottery_time") is None


def test_local_refresh_sets_draw_tag_for_participated(tmp_path: Path, monkeypatch) -> None:
    now = 1_700_000_000
    monkeypatch.setattr("src.status_refresh.time.time", lambda: now)

    path = tmp_path / "enriched_latest.json"
    item = _activity("soon-1", lottery_time=now + 3600)
    _write_enriched(path, activities=[item])

    participations = {
        "soon-1": ParticipationRecord(dynamic_id="soon-1", user_status="已参加", updated_at=1),
    }
    monkeypatch.setattr("src.status_refresh.load_participations", lambda: participations)

    result = refresh_local_activity_statuses(path=path)

    assert result["soon_marked"] == 1
    refreshed = json.loads(path.read_text(encoding="utf-8"))["activities"][0]
    assert refreshed["activity_status"] == "已参加"
    assert refreshed["draw_tag"] == "即将开奖"


def test_local_refresh_leaves_unlisted_activity_unchanged(tmp_path: Path, monkeypatch) -> None:
    now = 1_700_000_000
    monkeypatch.setattr("src.status_refresh.time.time", lambda: now)

    path = tmp_path / "enriched_latest.json"
    active = _activity("active-1", lottery_time=now + 3600, activity_status="未参加")
    ended = _activity("ended-1", lottery_time=now - 10, draw_status="ended", activity_status="已结束")
    _write_enriched(path, activities=[active, ended])

    result = refresh_local_activity_statuses(path=path)

    assert result["scanned"] == 1
    by_id = {item["dynamic_id"]: item for item in json.loads(path.read_text(encoding="utf-8"))["activities"]}
    assert by_id["active-1"]["activity_status"] == "未参加"
    assert by_id["ended-1"]["activity_status"] == "已结束"


def test_backfill_missing_lottery_times(tmp_path: Path, monkeypatch) -> None:
    from src.lottery_time import SIX_MONTHS_SECONDS

    path = tmp_path / "enriched_latest.json"
    participate_at = 1_600_000_000
    item = _activity("bf-1", lottery_time=None, enriched_at=participate_at)
    _write_enriched(path, activities=[item])

    participations = {
        "bf-1": ParticipationRecord(dynamic_id="bf-1", user_status="已参加", updated_at=participate_at),
    }
    monkeypatch.setattr("src.status_refresh.load_participations", lambda: participations)

    result = backfill_missing_lottery_times(path=path)

    assert result["updated"] == 1
    refreshed = json.loads(path.read_text(encoding="utf-8"))["activities"][0]
    assert refreshed["lottery_time"] == participate_at + SIX_MONTHS_SECONDS
