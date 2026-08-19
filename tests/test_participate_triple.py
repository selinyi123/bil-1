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


def _reserve_actions(*, ok: bool = True, follow_ok: bool = True) -> list[dict]:
    return [
        {"action": "follow", "ok": follow_ok, "detail": "" if follow_ok else "关注失败"},
        {"action": "reserve", "ok": ok, "detail": "" if ok else "预约失败"},
    ]


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
    assert participate_step_budget("预约抽奖") == 2
    assert participate_step_budget("互动抽奖") == 5
    with patch("web.activity_service.lookup_lottery_type", return_value="预约抽奖"):
        assert participate_step_budget("", dynamic_id=_id(9)) == 2


def test_build_triple_progress_plan_mixed_types() -> None:
    targets = [
        _row(_id(1), can_participate=True, lottery_type="预约抽奖"),
        _row(_id(2), can_participate=True, lottery_type="互动抽奖"),
    ]
    total, plan = build_triple_progress_plan(targets)
    assert total == 7
    assert plan[_id(1)] == (0, 2)
    assert plan[_id(2)] == (2, 5)


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


def test_run_action_participate_triple_concurrent(monkeypatch: pytest.MonkeyPatch) -> None:
    targets = [_row(_id(101), can_participate=True), _row(_id(102), can_participate=True)]
    calls: list[str] = []
    client_instances: list[object] = []

    class FakeClient:
        def __enter__(self):
            client_instances.append(self)
            return self

        def __exit__(self, *_args):
            return False

    def fake_execute(dynamic_id: str, on_step, *, lottery_type: str | None = None, client=None) -> dict:
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
        patch("web.actions.ensure_activity_participatable"),
        patch("web.actions._execute_participate", side_effect=fake_execute),
        patch("web.actions.mark_enriched_joined"),
        patch("web.actions.refresh_local_activity_statuses"),
        patch("web.actions.BilibiliClient", FakeClient),
    ):
        payload = run_action("participate_triple", {}, on_progress=on_progress)

    assert set(calls) == {_id(101), _id(102)}
    assert len(calls) == 2
    assert len(client_instances) == 2
    assert payload["ok"] is True
    assert payload["result"]["joined"] == 2
    assert len(payload["result"]["items"]) == 2


def test_run_action_participate_triple_fail_fast_stops_other_targets() -> None:
    import time

    targets = [_row(_id(401), can_participate=True), _row(_id(402), can_participate=True)]
    progress_messages: list[str] = []

    def fake_execute(dynamic_id: str, on_step, *, lottery_type: str | None = None, client=None) -> dict:
        if dynamic_id == _id(401):
            time.sleep(0.4)
        if dynamic_id == _id(402):
            raise RuntimeError("模拟参与失败")
        on_step(1, 5, f"{dynamic_id} 点赞", "like")
        return {
            "dynamic_id": dynamic_id,
            "status": "joined",
            "message": "完成",
            "actions": _interact_actions(),
            "lottery_type": "互动抽奖",
        }

    def on_progress(**kwargs) -> None:
        message = kwargs.get("message")
        if message:
            progress_messages.append(str(message))

    with (
        patch("web.actions.pick_triple_participate_targets", return_value=targets),
        patch("web.actions.resolve_participate_lottery_type", return_value="互动抽奖"),
        patch("web.actions.ensure_activity_participatable"),
        patch("web.actions._execute_participate", side_effect=fake_execute),
        patch("web.actions.mark_enriched_joined"),
        patch("web.actions.refresh_local_activity_statuses"),
        patch("web.actions.BilibiliClient"),
    ):
        with pytest.raises(RuntimeError, match="模拟参与失败"):
            run_action("participate_triple", {}, on_progress=on_progress)

    combined = "\n".join(progress_messages)
    assert "失败" in combined
    assert "已停止" in combined


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
        patch("web.actions.ensure_activity_participatable"),
        patch("web.actions._execute_participate", return_value=fake_payload),
        patch("web.actions.resolve_participate_lottery_type", return_value="互动抽奖"),
        patch("web.actions.mark_enriched_joined"),
        patch("web.actions.refresh_local_activity_statuses"),
        patch("web.actions.BilibiliClient"),
    ):
        with pytest.raises(RuntimeError):
            run_action("participate_triple", {}, on_progress=lambda **_kwargs: None)


def test_run_action_participate_triple_uses_mixed_progress_budget() -> None:
    targets = [
        _row(_id(1), can_participate=True, lottery_type="预约抽奖"),
        _row(_id(2), can_participate=True, lottery_type="互动抽奖"),
    ]
    progress_totals: list[int] = []

    def fake_execute(dynamic_id: str, on_step, *, lottery_type: str | None = None, client=None) -> dict:
        if dynamic_id == _id(1):
            on_step(1, 2, "正在关注（1/2）", "follow")
            on_step(2, 2, "正在预约（2/2）", "reserve")
            return {
                "dynamic_id": dynamic_id,
                "status": "joined",
                "message": "关注与预约均已完成",
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
        patch("web.actions.ensure_activity_participatable"),
        patch("web.actions._execute_participate", side_effect=fake_execute),
        patch("web.actions.mark_enriched_joined"),
        patch("web.actions.refresh_local_activity_statuses"),
        patch("web.actions.BilibiliClient"),
    ):
        run_action("participate_triple", {}, on_progress=on_progress)

    assert progress_totals
    assert progress_totals[0] == 7


def test_run_action_participate_triple_emits_targets_in_initial_progress() -> None:
    targets = [
        _row(_id(1), can_participate=True, lottery_type="预约抽奖"),
        _row(_id(2), can_participate=True, lottery_type="互动抽奖"),
    ]
    progress_targets: list[list[dict]] = []

    def fake_execute(dynamic_id: str, on_step, *, lottery_type: str | None = None, client=None) -> dict:
        on_step(1, 2 if dynamic_id == _id(1) else 5, "进行中", "follow")
        return {
            "dynamic_id": dynamic_id,
            "status": "joined",
            "message": "完成",
            "actions": _reserve_actions() if dynamic_id == _id(1) else _interact_actions(),
            "lottery_type": "预约抽奖" if dynamic_id == _id(1) else "互动抽奖",
        }

    def on_progress(**kwargs) -> None:
        patch = kwargs.get("result_patch")
        if isinstance(patch, dict) and patch.get("targets"):
            progress_targets.append(list(patch["targets"]))

    with (
        patch("web.actions.pick_triple_participate_targets", return_value=targets),
        patch("src.participate_enhance.load_participate_enhance", return_value={"shuffle_targets": False}),
        patch("web.actions.resolve_participate_lottery_type", side_effect=lambda dynamic_id, **_: "预约抽奖" if dynamic_id == _id(1) else "互动抽奖"),
        patch("web.actions.ensure_activity_participatable"),
        patch("web.actions._execute_participate", side_effect=fake_execute),
        patch("web.actions.mark_enriched_joined"),
        patch("web.actions.refresh_local_activity_statuses"),
        patch("web.actions.BilibiliClient"),
    ):
        run_action("participate_triple", {}, on_progress=on_progress)

    assert progress_targets
    emitted = progress_targets[0]
    assert len(emitted) == 2
    assert emitted[0]["lottery_type"] == "预约抽奖"
    assert emitted[1]["lottery_type"] == "互动抽奖"


def test_run_action_participate_triple_requires_targets() -> None:
    with patch("web.actions.pick_triple_participate_targets", return_value=[]):
        payload = run_action("participate_triple", {})
    assert payload["ok"] is True
    assert payload["result"]["skipped"] is True
    assert "跳过" in payload["message"]


def test_run_action_participate_triple_uses_lookup_type_for_execution() -> None:
    targets = [_row(_id(301), can_participate=True, lottery_type="互动抽奖")]
    captured_types: list[str | None] = []

    def fake_execute(
        dynamic_id: str,
        on_step,
        *,
        lottery_type: str | None = None,
        client=None,
    ) -> dict:
        captured_types.append(lottery_type)
        on_step(1, 2, "正在关注（1/2）", "follow")
        on_step(2, 2, "正在预约（2/2）", "reserve")
        return {
            "dynamic_id": dynamic_id,
            "status": "joined",
            "message": "关注与预约均已完成",
            "actions": _reserve_actions(),
            "lottery_type": "预约抽奖",
        }

    with (
        patch("web.actions.pick_triple_participate_targets", return_value=targets),
        patch("web.actions.resolve_participate_lottery_type", return_value="预约抽奖"),
        patch("web.actions.ensure_activity_participatable"),
        patch("web.actions._execute_participate", side_effect=fake_execute),
        patch("web.actions.mark_enriched_joined"),
        patch("web.actions.refresh_local_activity_statuses"),
        patch("web.actions.BilibiliClient"),
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


def test_run_action_participate_triple_internal_failure_does_not_set_cancel_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """核心不变量：三连内部失败绝不能 set cancel_event（否则 JobRunner 误判为 cancelled）。

    只有用户取消（外部 set cancel_event）才能产生 cancelled。
    """
    import threading

    targets = [_row(_id(501), can_participate=True), _row(_id(502), can_participate=True)]
    cancel_event = threading.Event()

    def fake_execute(dynamic_id: str, on_step, *, lottery_type: str | None = None, client=None) -> dict:
        if dynamic_id == _id(502):
            raise RuntimeError("评论 API 报错")
        return {
            "dynamic_id": dynamic_id,
            "status": "joined",
            "message": "完成",
            "actions": _interact_actions(),
            "lottery_type": "互动抽奖",
        }

    with (
        patch("web.actions.pick_triple_participate_targets", return_value=targets),
        patch("web.actions.resolve_participate_lottery_type", return_value="互动抽奖"),
        patch("web.actions.ensure_activity_participatable"),
        patch("web.actions._execute_participate", side_effect=fake_execute),
        patch("web.actions.mark_enriched_joined"),
        patch("web.actions.refresh_local_activity_statuses"),
        patch("web.actions.BilibiliClient"),
    ):
        with pytest.raises(RuntimeError, match="三连参与失败"):
            run_action("participate_triple", {}, on_progress=lambda **_kwargs: None, cancel_event=cancel_event)

    # 内部失败 ≠ 用户取消：cancel_event 必须保持未设置
    assert not cancel_event.is_set()


def test_run_action_participate_triple_partial_failure_carries_completed() -> None:
    """partial_failure 语义：失败时异常携带已完成活动摘要（副作用不可回滚，必须可追溯）。"""
    import time as time_mod

    from web.actions import TripleParticipateFailed

    targets = [_row(_id(601), can_participate=True), _row(_id(602), can_participate=True)]

    def fake_execute(dynamic_id: str, on_step, *, lottery_type: str | None = None, client=None) -> dict:
        if dynamic_id == _id(601):
            # 601 先完成，产生真实外部副作用
            return {
                "dynamic_id": dynamic_id,
                "status": "joined",
                "message": "完成",
                "actions": _interact_actions(),
                "lottery_type": "互动抽奖",
            }
        if dynamic_id == _id(602):
            time_mod.sleep(0.3)  # 保证 601 先落进 results
            raise RuntimeError("评论 API 报错")
        raise AssertionError("unexpected dynamic_id")

    with (
        patch("web.actions.pick_triple_participate_targets", return_value=targets),
        patch("web.actions.resolve_participate_lottery_type", return_value="互动抽奖"),
        patch("web.actions.ensure_activity_participatable"),
        patch("web.actions._execute_participate", side_effect=fake_execute),
        patch("web.actions.mark_enriched_joined"),
        patch("web.actions.refresh_local_activity_statuses"),
        patch("web.actions.BilibiliClient"),
    ):
        with pytest.raises(TripleParticipateFailed) as excinfo:
            run_action("participate_triple", {}, on_progress=lambda **_kwargs: None)

    exc = excinfo.value
    assert exc.failed_dynamic_id == _id(602)
    assert len(exc.completed) == 1
    completed = exc.completed[0]
    assert completed["dynamic_id"] == _id(601)
    actions = completed["actions"]
    assert {"action": "repost", "ok": True} in actions
    assert {"action": "follow", "ok": True} in actions


def test_run_action_participate_triple_partial_reports_started_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#9：失败活动已开始执行的外部副作用（on_step 已上报）必须出现在异常摘要中。"""
    import time as time_mod

    from web.actions import TripleParticipateFailed

    targets = [_row(_id(701), can_participate=True), _row(_id(702), can_participate=True)]

    def fake_execute(dynamic_id: str, on_step, *, lottery_type: str | None = None, client=None) -> dict:
        if dynamic_id == _id(701):
            return {
                "dynamic_id": dynamic_id,
                "status": "joined",
                "message": "完成",
                "actions": _interact_actions(),
                "lottery_type": "互动抽奖",
            }
        if dynamic_id == _id(702):
            time_mod.sleep(0.2)  # 保证 701 先完成
            # 点赞、关注已开始执行（真实外部副作用），随后评论步骤抛错
            on_step(1, 5, f"{dynamic_id} 正在点赞（1/5）", "like")
            on_step(2, 5, f"{dynamic_id} 正在关注（2/5）", "follow")
            raise RuntimeError("评论 API 报错")
        raise AssertionError("unexpected dynamic_id")

    with (
        patch("web.actions.pick_triple_participate_targets", return_value=targets),
        patch("web.actions.resolve_participate_lottery_type", return_value="互动抽奖"),
        patch("web.actions.ensure_activity_participatable"),
        patch("web.actions._execute_participate", side_effect=fake_execute),
        patch("web.actions.mark_enriched_joined"),
        patch("web.actions.refresh_local_activity_statuses"),
        patch("web.actions.BilibiliClient"),
    ):
        with pytest.raises(TripleParticipateFailed) as excinfo:
            run_action("participate_triple", {}, on_progress=lambda **_kwargs: None)

    exc = excinfo.value
    assert exc.failed_dynamic_id == _id(702)
    # 已完成活动仍按原结构返回
    completed_ids = [item["dynamic_id"] for item in exc.completed]
    assert _id(701) in completed_ids
    # 未完成但已开始动作的活动以 partial: true 如实上报
    partials = [item for item in exc.completed if item.get("partial") is True]
    assert len(partials) == 1
    partial = partials[0]
    assert partial["dynamic_id"] == _id(702)
    assert partial["actions"] == [
        {"action": "like", "ok": None, "partial": True},
        {"action": "follow", "ok": None, "partial": True},
    ]


def test_run_action_participate_triple_partial_dedupes_started_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#9：同一动作名多次上报只记录一次（去重）。"""
    import time as time_mod

    from web.actions import TripleParticipateFailed

    targets = [_row(_id(801), can_participate=True), _row(_id(802), can_participate=True)]

    def fake_execute(dynamic_id: str, on_step, *, lottery_type: str | None = None, client=None) -> dict:
        if dynamic_id == _id(801):
            return {
                "dynamic_id": dynamic_id,
                "status": "joined",
                "message": "完成",
                "actions": _interact_actions(),
                "lottery_type": "互动抽奖",
            }
        if dynamic_id == _id(802):
            time_mod.sleep(0.2)
            on_step(1, 5, f"{dynamic_id} 正在点赞（1/5）", "like")
            on_step(2, 5, f"{dynamic_id} 正在点赞（2/5）", "like")
            on_step(3, 5, f"{dynamic_id} 正在关注（3/5）", "follow")
            raise RuntimeError("转发 API 报错")
        raise AssertionError("unexpected dynamic_id")

    with (
        patch("web.actions.pick_triple_participate_targets", return_value=targets),
        patch("web.actions.resolve_participate_lottery_type", return_value="互动抽奖"),
        patch("web.actions.ensure_activity_participatable"),
        patch("web.actions._execute_participate", side_effect=fake_execute),
        patch("web.actions.mark_enriched_joined"),
        patch("web.actions.refresh_local_activity_statuses"),
        patch("web.actions.BilibiliClient"),
    ):
        with pytest.raises(TripleParticipateFailed) as excinfo:
            run_action("participate_triple", {}, on_progress=lambda **_kwargs: None)

    partial = next(item for item in excinfo.value.completed if item.get("partial") is True)
    assert partial["actions"] == [
        {"action": "like", "ok": None, "partial": True},
        {"action": "follow", "ok": None, "partial": True},
    ]


