from __future__ import annotations

from unittest.mock import patch

import pytest

from web.actions import run_action
from web.activity_service import (
    build_triple_progress_plan,
    participate_step_budget,
    pick_triple_participate_targets,
    summarize_triple_participate_targets,
)


def _id(n: int) -> str:
    return f"100000000000000{n:03d}"


def _interact_actions(*, repost_ok: bool = True, comment_ok: bool = True) -> list[dict]:
    return [
        {"action": "like", "ok": True, "detail": ""},
        {"action": "follow", "ok": True, "detail": ""},
        {"action": "favorite", "ok": True, "detail": ""},
        {"action": "repost", "ok": repost_ok, "detail": "" if repost_ok else "转发失败"},
        {"action": "comment", "ok": comment_ok, "detail": ""},
    ]


def _reserve_actions(*, ok: bool = True) -> list[dict]:
    return [{"action": "reserve", "ok": ok, "detail": "" if ok else "预约失败"}]


def _row(dynamic_id: str, *, can_participate: bool, lottery_type: str = "互动抽奖") -> dict:
    return {
        "dynamic_id": dynamic_id,
        "activity_title": f"活动 {dynamic_id[-3:]}",
        "lottery_type": lottery_type,
        "activity_status": "未参加" if can_participate else "已参加",
        "draw_status": "active",
        "can_participate": can_participate,
    }


def test_participate_step_budget() -> None:
    assert participate_step_budget("预约抽奖") == 1
    assert participate_step_budget("互动抽奖") == 5
    with patch("web.activity_service.lookup_lottery_type", return_value="预约抽奖"):
        assert participate_step_budget("", dynamic_id=_id(9)) == 1


def test_build_triple_progress_plan_mixed_types() -> None:
    targets = [
        _row(_id(1), can_participate=True, lottery_type="预约抽奖"),
        _row(_id(2), can_participate=True, lottery_type="互动抽奖"),
    ]
    total, plan = build_triple_progress_plan(targets)
    assert total == 6
    assert plan[_id(1)] == (0, 1)
    assert plan[_id(2)] == (1, 5)


def test_pick_triple_participate_targets_skips_non_participatable() -> None:
    rows = [
        _row(_id(1), can_participate=False),
        _row(_id(2), can_participate=True),
        _row(_id(3), can_participate=True),
        _row(_id(4), can_participate=True),
        _row(_id(5), can_participate=True),
    ]
    with patch("web.activity_service._filtered_activity_rows", return_value=rows) as mock_filter:
        targets = pick_triple_participate_targets()
    mock_filter.assert_called_once_with(
        status=None,
        lottery_type=None,
        draw=None,
        draw_window=None,
        q=None,
        sort=None,
        order=None,
    )
    assert [item["dynamic_id"] for item in targets] == [_id(2), _id(3), _id(4)]


def test_pick_triple_participate_targets_follows_list_filters() -> None:
    rows = [_row(_id(1), can_participate=True, lottery_type="转发抽奖")]
    with patch("web.activity_service._filtered_activity_rows", return_value=rows) as mock_filter:
        pick_triple_participate_targets(lottery_type="转发抽奖", sort="heat", order="desc")
    mock_filter.assert_called_once_with(
        status=None,
        lottery_type="转发抽奖",
        draw=None,
        draw_window=None,
        q=None,
        sort="heat",
        order="desc",
    )


def test_pick_triple_participate_targets_only_picks_not_joined() -> None:
    rows = [
        {**_row(_id(1), can_participate=True), "activity_status": "未参加"},
        {**_row(_id(2), can_participate=False), "activity_status": "已参加"},
    ]
    with patch("web.activity_service._filtered_activity_rows", return_value=rows) as mock_filter:
        targets = pick_triple_participate_targets(status="未参加")
    mock_filter.assert_called_once_with(
        status="未参加",
        lottery_type=None,
        draw=None,
        draw_window=None,
        q=None,
        sort=None,
        order=None,
    )
    assert [item["dynamic_id"] for item in targets] == [_id(1)]


def test_pick_triple_participate_targets_empty_when_joined_filter() -> None:
    rows = [
        {**_row(_id(1), can_participate=False), "activity_status": "已参加"},
        {**_row(_id(2), can_participate=False), "activity_status": "已参加"},
    ]
    with patch("web.activity_service._filtered_activity_rows", return_value=rows):
        targets = pick_triple_participate_targets(status="已参加")
    assert targets == []


def test_list_activities_includes_triple_targets_from_same_filters() -> None:
    from web.activity_service import list_activities

    rows = [
        {**_row(_id(1), can_participate=False), "activity_status": "已参加"},
        {**_row(_id(2), can_participate=False), "activity_status": "已参加"},
    ]
    with patch("web.activity_service._filtered_activity_rows", return_value=rows):
        payload = list_activities(status="已参加")
    assert payload["total"] == 2
    assert payload["triple_targets"]["count"] == 0
    assert payload["triple_targets"]["items"] == []


def test_pick_triple_participate_targets_dedupes_and_skips_invalid() -> None:
    rows = [
        _row("invalid", can_participate=True),
        _row(_id(1), can_participate=True),
        _row(_id(1), can_participate=True),
        _row(_id(2), can_participate=True, lottery_type="充电抽奖"),
        _row(_id(3), can_participate=True),
    ]
    with patch("web.activity_service._filtered_activity_rows", return_value=rows):
        targets = pick_triple_participate_targets()
    assert [item["dynamic_id"] for item in targets] == [_id(1), _id(3)]


def test_pick_triple_participate_targets_respects_limit() -> None:
    rows = [_row(_id(i), can_participate=True) for i in range(1, 6)]
    with patch("web.activity_service._filtered_activity_rows", return_value=rows):
        targets = pick_triple_participate_targets(limit=2)
    assert len(targets) == 2
    assert targets[0]["dynamic_id"] == _id(1)


def test_summarize_triple_participate_targets() -> None:
    rows = [_row(_id(1), can_participate=True), _row(_id(2), can_participate=True)]
    with patch("web.activity_service._filtered_activity_rows", return_value=rows):
        summary = summarize_triple_participate_targets()
    assert summary["count"] == 2
    assert summary["limit"] == 3
    assert len(summary["items"]) == 2
    assert summary["items"][0]["dynamic_id"] == _id(1)


def test_run_action_participate_triple_sequential(monkeypatch: pytest.MonkeyPatch) -> None:
    targets = [_row(_id(101), can_participate=True), _row(_id(102), can_participate=True)]
    calls: list[str] = []

    def fake_execute(dynamic_id: str, on_step, *, lottery_type: str | None = None) -> dict:
        calls.append(dynamic_id)
        on_step(1, 5, f"{dynamic_id} 点赞", "like")
        return {
            "dynamic_id": dynamic_id,
            "status": "joined",
            "message": "完成",
            "actions": _interact_actions(),
            "lottery_type": "互动抽奖",
        }

    progress_messages: list[str] = []

    def on_progress(**kwargs) -> None:
        message = kwargs.get("message")
        if message:
            progress_messages.append(str(message))

    with (
        patch("web.actions.pick_triple_participate_targets", return_value=targets),
        patch("web.actions.resolve_participate_lottery_type", return_value="互动抽奖"),
        patch("web.actions._execute_participate", side_effect=fake_execute),
        patch("web.actions.invalidate_activity_cache"),
    ):
        payload = run_action("participate_triple", {}, on_progress=on_progress)

    assert calls == [_id(101), _id(102)]
    assert payload["ok"] is True
    assert payload["result"]["joined"] == 2
    assert len(payload["result"]["items"]) == 2


def test_run_action_participate_triple_rejects_joined_with_failed_core_action() -> None:
    targets = [_row(_id(201), can_participate=True)]
    fake_payload = {
        "dynamic_id": _id(201),
        "status": "joined",
        "message": "评论受限，已视为参与成功",
        "actions": _interact_actions(repost_ok=False, comment_ok=False),
        "lottery_type": "互动抽奖",
    }

    with (
        patch("web.actions.pick_triple_participate_targets", return_value=targets),
        patch("web.actions._execute_participate", return_value=fake_payload),
        patch("web.actions.resolve_participate_lottery_type", return_value="互动抽奖"),
        patch("web.actions.invalidate_activity_cache"),
    ):
        payload = run_action("participate_triple", {}, on_progress=lambda **_kwargs: None)

    item = payload["result"]["items"][0]
    assert item["status"] == "failed"
    assert payload["result"]["joined"] == 0
    assert payload["result"]["failed"] == 1
    assert payload["ok"] is False


def test_run_action_participate_triple_uses_mixed_progress_budget() -> None:
    targets = [
        _row(_id(1), can_participate=True, lottery_type="预约抽奖"),
        _row(_id(2), can_participate=True, lottery_type="互动抽奖"),
    ]
    progress_totals: list[int] = []

    def fake_execute(dynamic_id: str, on_step, *, lottery_type: str | None = None) -> dict:
        if dynamic_id == _id(1):
            on_step(1, 1, "正在预约直播…", "reserve")
            return {
                "dynamic_id": dynamic_id,
                "status": "joined",
                "message": "预约成功",
                "actions": _reserve_actions(),
                "lottery_type": "预约抽奖",
            }
        on_step(1, 5, "进行中", "like")
        return {
            "dynamic_id": dynamic_id,
            "status": "joined",
            "message": "完成",
            "actions": _interact_actions(),
            "lottery_type": "互动抽奖",
        }

    def on_progress(**kwargs) -> None:
        total = kwargs.get("total")
        if total is not None:
            progress_totals.append(int(total))

    with (
        patch("web.actions.pick_triple_participate_targets", return_value=targets),
        patch("web.actions.resolve_participate_lottery_type", side_effect=lambda dynamic_id, **_: "预约抽奖" if dynamic_id == _id(1) else "互动抽奖"),
        patch("web.actions._execute_participate", side_effect=fake_execute),
        patch("web.actions.invalidate_activity_cache"),
    ):
        run_action("participate_triple", {}, on_progress=on_progress)

    assert progress_totals
    assert progress_totals[0] == 6


def test_run_action_participate_triple_requires_targets() -> None:
    with patch("web.actions.pick_triple_participate_targets", return_value=[]):
        with pytest.raises(ValueError, match="没有可参与"):
            run_action("participate_triple", {})


def test_run_action_participate_triple_uses_lookup_type_for_execution() -> None:
    targets = [_row(_id(301), can_participate=True, lottery_type="互动抽奖")]
    captured_types: list[str | None] = []

    def fake_execute(
        dynamic_id: str,
        on_step,
        *,
        lottery_type: str | None = None,
    ) -> dict:
        captured_types.append(lottery_type)
        on_step(1, 1, "正在预约直播…", "reserve")
        return {
            "dynamic_id": dynamic_id,
            "status": "joined",
            "message": "预约成功",
            "actions": _reserve_actions(),
            "lottery_type": "预约抽奖",
        }

    with (
        patch("web.actions.pick_triple_participate_targets", return_value=targets),
        patch("web.actions.resolve_participate_lottery_type", return_value="预约抽奖"),
        patch("web.actions._execute_participate", side_effect=fake_execute),
        patch("web.actions.invalidate_activity_cache"),
    ):
        payload = run_action("participate_triple", {}, on_progress=lambda **_kwargs: None)

    assert captured_types == ["预约抽奖"]
    assert payload["ok"] is True
    assert payload["result"]["joined"] == 1
    item = payload["result"]["items"][0]
    assert item["lottery_type"] == "预约抽奖"
    assert item["actions"] == _reserve_actions()


def test_run_action_participate_triple_cancelled_before_start() -> None:
    import threading

    cancel_event = threading.Event()
    cancel_event.set()
    with patch("web.actions.pick_triple_participate_targets", return_value=[_row(_id(1), can_participate=True)]):
        with pytest.raises(ValueError, match="已取消"):
            run_action("participate_triple", {}, cancel_event=cancel_event)
