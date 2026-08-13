from __future__ import annotations

import time

import pytest
from sqlmodel import select

from src.activity_store import replace_all_activities
from src.db.models import ActivityRow, ParticipationActionRow, ParticipationRow
from src.db.session import session_scope
from src.db.uids import participation_uid
from src.lottery_actions import ActionResult
from src.participation import (
    ParticipateResult,
    _persist_result,
    record_participation_outcome_unlocked,
)
from src.participation_log import ParticipationActionRecord, participation_succeeded


def _ok(action: str) -> ActionResult:
    return ActionResult(action, True, "ok")


def _fail(action: str, detail: str) -> ActionResult:
    return ActionResult(action, False, detail)


def _activity(dynamic_id: str, *, lottery_type: str = "互动抽奖") -> dict:
    return {
        "dynamic_id": dynamic_id,
        "source_url": "https://t.bilibili.com/" + dynamic_id,
        "lottery_type": lottery_type,
        "draw_status": "active",
        "lottery_time": int(time.time()) + 3600,
        "activity_status": "未参加",
        "draw_tag": "",
        "status_classified": True,
        "prizes": [{"description": "测试奖品", "winner_count": 1}],
    }


def _record(dynamic_id: str, *, status: str = "joined", recorded_at: int | None = None) -> ParticipationActionRecord:
    return ParticipationActionRecord(
        recorded_at=int(recorded_at if recorded_at is not None else time.time()),
        dynamic_id=dynamic_id,
        lottery_type="互动抽奖",
        status=status,
        message="核心操作均已完成",
        action_text="测试文案",
        actions=[{"action": "like", "ok": True, "detail": ""}],
        context_snapshot={},
    )


def test_interact_succeeds_when_comment_blocked_by_follow_days() -> None:
    actions = [
        _ok("like"),
        _ok("follow"),
        _ok("favorite"),
        _ok("repost"),
        _fail("comment", "code=12078 关注UP主7天以上的人可发评论"),
    ]
    assert participation_succeeded(actions, lottery_type="互动抽奖") is True


def test_interact_fails_when_core_action_missing() -> None:
    actions = [
        _ok("like"),
        _ok("follow"),
        _ok("favorite"),
        _fail("repost", "code=1"),
        _fail("comment", "code=12078 关注UP主7天以上的人可发评论"),
    ]
    assert participation_succeeded(actions, lottery_type="互动抽奖") is False


def test_interact_fails_when_comment_fails_for_other_reason() -> None:
    actions = [
        _ok("like"),
        _ok("follow"),
        _ok("favorite"),
        _ok("repost"),
        _fail("comment", "code=999 评论内容违规"),
    ]
    assert participation_succeeded(actions, lottery_type="互动抽奖") is False


def test_repost_requires_all_five_actions() -> None:
    actions = [
        _ok("like"),
        _ok("follow"),
        _ok("favorite"),
        _ok("repost"),
        _fail("comment", "code=12078 关注UP主7天以上的人可发评论"),
    ]
    assert participation_succeeded(actions, lottery_type="转发抽奖") is False


def test_reserve_lottery_requires_follow_and_reserve() -> None:
    actions = [_ok("follow"), _ok("reserve")]
    assert participation_succeeded(actions, lottery_type="预约抽奖") is True


def test_reserve_lottery_fails_when_follow_missing() -> None:
    actions = [_ok("reserve")]
    assert participation_succeeded(actions, lottery_type="预约抽奖") is False


def test_reserve_lottery_fails_when_follow_fails() -> None:
    actions = [_fail("follow", "code=1"), _ok("reserve")]
    assert participation_succeeded(actions, lottery_type="预约抽奖") is False


def test_reserve_lottery_fails_when_reserve_missing() -> None:
    actions = [_ok(name) for name in ("like", "follow", "favorite", "repost", "comment")]
    assert participation_succeeded(actions, lottery_type="预约抽奖") is False


def test_reserve_lottery_fails_when_reserve_fails() -> None:
    actions = [_ok("follow"), _fail("reserve", "预约失败")]
    assert participation_succeeded(actions, lottery_type="预约抽奖") is False


def test_record_participation_outcome_writes_all_tables_in_one_transaction(
    isolated_home,
) -> None:
    """#12：单事务内一次参与应保证 actions / participations / activities 三表一致。"""
    replace_all_activities([_activity("1000000000000000001")])
    uid = participation_uid()
    record = _record("1000000000000000001")

    record_participation_outcome_unlocked(record, mark_joined=True)

    with session_scope() as session:
        action_rows = session.exec(
            select(ParticipationActionRow).where(ParticipationActionRow.uid == uid)
        ).all()
        assert len(action_rows) == 1
        assert action_rows[0].dynamic_id == "1000000000000000001"
        assert action_rows[0].status == "joined"

        part_rows = session.exec(
            select(ParticipationRow).where(ParticipationRow.uid == uid)
        ).all()
        assert len(part_rows) == 1
        assert part_rows[0].user_status == "已参加"
        assert part_rows[0].source == "participate"

        activity_row = session.get(ActivityRow, "1000000000000000001")
        assert activity_row is not None
        assert activity_row.activity_status == "已参加"
        assert activity_row.draw_tag == ""
        assert activity_row.status_classified is True


def test_record_participation_outcome_skips_status_tables_when_not_joined(
    isolated_home,
) -> None:
    """未参与成功时只写动作日志，不改 participations 与 activities。"""
    replace_all_activities([_activity("1000000000000000002")])
    uid = participation_uid()
    record = _record("1000000000000000002", status="failed")

    record_participation_outcome_unlocked(record, mark_joined=False)

    with session_scope() as session:
        action_rows = session.exec(
            select(ParticipationActionRow).where(ParticipationActionRow.uid == uid)
        ).all()
        assert len(action_rows) == 1
        part_rows = session.exec(
            select(ParticipationRow).where(ParticipationRow.uid == uid)
        ).all()
        assert part_rows == []
        activity_row = session.get(ActivityRow, "1000000000000000002")
        assert activity_row.activity_status == "未参加"


def test_account_bound_participation_does_not_mutate_shared_activity_status(
    isolated_home,
) -> None:
    baseline = _activity("1000000000000000099")
    baseline_status = baseline["activity_status"]
    replace_all_activities([baseline])
    record = _record("1000000000000000099")

    record_participation_outcome_unlocked(
        record,
        account_uid="123456",
        mark_joined=True,
    )

    with session_scope() as session:
        action_rows = session.exec(
            select(ParticipationActionRow).where(ParticipationActionRow.uid == "123456")
        ).all()
        part_row = session.get(ParticipationRow, ("123456", "1000000000000000099"))
        activity_row = session.get(ActivityRow, "1000000000000000099")
        shared_status = activity_row.activity_status if activity_row is not None else None

    assert len(action_rows) == 1
    assert part_row is not None
    assert activity_row is not None
    assert shared_status == baseline_status


def test_record_participation_outcome_rolls_back_when_activity_write_fails(
    isolated_home, monkeypatch
) -> None:
    """#12：activities 更新抛错时整个事务回滚，前两表也不产生部分写入。"""
    replace_all_activities([_activity("1000000000000000003")])
    uid = participation_uid()

    def _boom(*_args, **_kwargs):
        raise RuntimeError("模拟 activities 更新失败")

    monkeypatch.setattr("src.participation.activity_dict_to_row", _boom)
    with pytest.raises(RuntimeError, match="模拟 activities 更新失败"):
        record_participation_outcome_unlocked(
            _record("1000000000000000003"),
            mark_joined=True,
        )

    with session_scope() as session:
        action_rows = session.exec(
            select(ParticipationActionRow).where(ParticipationActionRow.uid == uid)
        ).all()
        assert action_rows == []
        part_rows = session.exec(
            select(ParticipationRow).where(ParticipationRow.uid == uid)
        ).all()
        assert part_rows == []


def test_record_participation_outcome_trims_to_max_entries(isolated_home) -> None:
    """复用 append 逻辑：按 uid 裁剪超量动作日志（最多 _MAX_ENTRIES_PER_UID 条）。"""
    uid = participation_uid()
    for index in range(505):
        record = _record(
            "1000000000000000001",
            status="skipped",
            recorded_at=1_700_000_000 + index,
        )
        record_participation_outcome_unlocked(record, mark_joined=False)

    with session_scope() as session:
        rows = session.exec(
            select(ParticipationActionRow).where(ParticipationActionRow.uid == uid)
        ).all()
        assert len(rows) == 500
