from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest

from src.activity_store import load_activities, replace_all_activities
from src.participation_store import ParticipationRecord
from src.status_refresh import (
    backfill_missing_lottery_times,
    persist_activity_record,
    refresh_local_activity_statuses,
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


def test_local_refresh_skips_charging_and_ended(isolated_home: Path, monkeypatch) -> None:
    now = 1_700_000_000
    monkeypatch.setattr("src.status_refresh.time.time", lambda: now)
    replace_all_activities(
        [
            _activity("c1", lottery_type="充电抽奖", lottery_time=now + 100),
            _activity("e1", lottery_time=now - 10, draw_status="ended", activity_status="已结束"),
            _activity("a1", lottery_time=now + 100),
        ]
    )
    result = refresh_local_activity_statuses()
    assert result["scanned"] == 1
    assert result["total"] == 3


def test_local_refresh_marks_past_activity_ended(isolated_home: Path, monkeypatch) -> None:
    now = 1_700_000_000
    monkeypatch.setattr("src.status_refresh.time.time", lambda: now)
    # 避免 load_activities 在读库时按当前时间预标记已结束，导致 refresh 跳过候选
    monkeypatch.setattr("src.activity_store._normalize_ended_by_time", lambda item, now=None: False)
    replace_all_activities([_activity("past", lottery_time=now - 1)])
    result = refresh_local_activity_statuses()
    assert result["ended_marked"] == 1
    items = load_activities()
    assert items[0]["activity_status"] == "已结束"
    assert items[0]["draw_status"] == "ended"


def test_local_refresh_skips_missing_lottery_time(isolated_home: Path, monkeypatch) -> None:
    now = 1_700_000_000
    monkeypatch.setattr("src.status_refresh.time.time", lambda: now)
    replace_all_activities([_activity("no-time")])
    result = refresh_local_activity_statuses()
    assert result["scanned"] == 0
    assert result["skipped"] is True


def test_local_refresh_sets_draw_tag_for_participated(isolated_home: Path, monkeypatch) -> None:
    now = 1_700_000_000
    monkeypatch.setattr("src.status_refresh.time.time", lambda: now)
    replace_all_activities(
        [_activity("soon", lottery_time=now + 3600, platform_participated=True, activity_status="已参加")]
    )
    participations = {
        "soon": ParticipationRecord(
            dynamic_id="soon",
            user_status="已参加",
            updated_at=now - 100,
        )
    }
    monkeypatch.setattr("src.status_refresh.load_participations", lambda: participations)
    result = refresh_local_activity_statuses()
    assert result["soon_marked"] >= 0
    item = load_activities()[0]
    assert item["activity_status"] == "已参加"


def test_local_refresh_leaves_unlisted_activity_unchanged(isolated_home: Path, monkeypatch) -> None:
    now = 1_700_000_000
    monkeypatch.setattr("src.status_refresh.time.time", lambda: now)
    replace_all_activities(
        [_activity("x", lottery_type="未知类型", lottery_time=now + 100, activity_status="未参加")]
    )
    before = load_activities()[0]
    refresh_local_activity_statuses()
    after = load_activities()[0]
    assert after["activity_status"] == before["activity_status"]


def test_backfill_missing_lottery_times(isolated_home: Path, monkeypatch) -> None:
    replace_all_activities([_activity("need-time", enriched_at=1_600_000_000)])
    participations = {
        "need-time": ParticipationRecord(
            dynamic_id="need-time",
            user_status="已参加",
            updated_at=1_600_000_000,
        )
    }
    monkeypatch.setattr("src.status_refresh.load_participations", lambda: participations)
    result = backfill_missing_lottery_times()
    assert result["updated"] >= 0
    assert result["total"] == 1


def test_persist_activity_record_parallel_writes(isolated_home: Path, monkeypatch) -> None:
    """并行写回不应再因 Windows replace 冲突失败。"""
    items = [
        _activity(f"p-{i}", lottery_time=9_999_999_999 + i, activity_status="未参加")
        for i in range(8)
    ]
    replace_all_activities(items)

    def _persist(item: dict) -> str:
        dynamic_id = str(item["dynamic_id"])
        updated = dict(item)
        updated["platform_participated"] = True
        persist_activity_record(
            updated,
            now=1_700_000_000,
            participation=ParticipationRecord(
                dynamic_id=dynamic_id,
                user_status="已参加",
                updated_at=1_700_000_000,
            ),
        )
        return dynamic_id

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_persist, item) for item in items]
        done = {future.result() for future in as_completed(futures)}

    assert done == {str(item["dynamic_id"]) for item in items}
    by_id = {str(row["dynamic_id"]): row for row in load_activities()}
    assert len(by_id) == 8
    for dynamic_id in done:
        assert by_id[dynamic_id]["platform_participated"] is True


def test_load_payload_is_pure_read_does_not_seed(isolated_home: Path) -> None:
    """#30：load_payload 为纯读——空库不再隐式 seed。"""
    from src.activity_store import activity_count, load_payload

    assert activity_count() == 0
    payload = load_payload()
    assert payload["activities"] == []
    assert payload["updated_at"] == 0
    # 读不写库：空库仍是空库
    assert activity_count() == 0


def test_load_payload_pure_read_does_not_mark_ended(isolated_home: Path, monkeypatch) -> None:
    """#30：load_payload 纯读不隐式改过期活动状态（也不更新 updated_at）。"""
    import time

    from src.activity_store import load_payload, refresh_expired_activity_statuses

    now = int(time.time())
    replace_all_activities([_activity("past", lottery_time=now - 100)])
    payload = load_payload()
    item = payload["activities"][0]
    assert item["activity_status"] == "未参加"
    assert item["draw_status"] == "active"

    # 再次读取并记录 updated_at，确认读路径无写副作用
    payload_before = load_payload()
    assert payload_before["updated_at"] == payload["updated_at"]
    assert load_payload()["activities"][0]["activity_status"] == "未参加"

    # 显式刷新后才标记结束
    changed = refresh_expired_activity_statuses()
    assert changed == 1
    after = load_activities()[0]
    assert after["activity_status"] == "已结束"
    assert after["draw_status"] == "ended"


def test_refresh_expired_activity_statuses_updates_updated_at(isolated_home: Path) -> None:
    """#30：显式 refresh 函数生效，且刷新会更新库级 updated_at。"""
    import time

    from src.activity_store import load_payload, refresh_expired_activity_statuses

    now = int(time.time())
    replace_all_activities([_activity("past", lottery_time=now - 100)])
    before = load_payload()["updated_at"]

    assert refresh_expired_activity_statuses() == 1
    after = load_payload()
    assert after["updated_at"] >= before
    assert after["activities"][0]["activity_status"] == "已结束"
    # 幂等：第二次无变更
    assert refresh_expired_activity_statuses() == 0
