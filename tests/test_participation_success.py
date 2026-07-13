from __future__ import annotations

from src.lottery_actions import ActionResult
from src.participation_log import participation_succeeded


def _ok(action: str) -> ActionResult:
    return ActionResult(action, True, "ok")


def _fail(action: str, detail: str) -> ActionResult:
    return ActionResult(action, False, detail)


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


def test_repost_succeeds_when_all_actions_ok() -> None:
    actions = [_ok(name) for name in ("like", "follow", "favorite", "repost", "comment")]
    assert participation_succeeded(actions, lottery_type="转发抽奖") is True
