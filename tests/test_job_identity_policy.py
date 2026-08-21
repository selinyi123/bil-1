"""Job 身份策略的守卫（SPEC 8）。

这条不变量此前只存在于代码与文档里，没有任何测试守它——策略表被改坏、
或新增 action 忘了登记时，不会有任何信号。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from web.job_runner import (
    IDENTITY_BOUND,
    IDENTITY_CONTEXT,
    IDENTITY_UNBOUND,
    JOB_IDENTITY_POLICY,
    JobRunner,
    job_identity_policy,
)
from web.schemas.jobs import ALLOWED_JOB_ACTIONS


def test_every_allowed_action_is_registered() -> None:
    """新增 action 必须显式登记身份策略，不能靠默认值蒙混过关。

    这条断言的作用不是检查当前实现，而是**让忘记登记的人立刻失败**。
    """
    unregistered = sorted(ALLOWED_JOB_ACTIONS - set(JOB_IDENTITY_POLICY))
    assert not unregistered, f"以下 action 未登记身份策略：{unregistered}"


def test_unregistered_action_defaults_to_bound_not_unbound() -> None:
    """默认值必须是拒绝放行的那一侧。

    若默认改成 unbound，任何忘了登记的新入口都会静默跳过身份守卫——
    这正是本策略表要消灭的 fail-open。
    """
    assert job_identity_policy("some_action_nobody_registered") == IDENTITY_BOUND


def test_only_login_is_unbound() -> None:
    unbound = {a for a, p in JOB_IDENTITY_POLICY.items() if p == IDENTITY_UNBOUND}
    assert unbound == {"login"}, f"意外的免身份 action：{unbound - {'login'}}"


def test_context_policy_covers_exactly_the_write_participation_actions() -> None:
    """只有真正代表用户向 B 站写入的参与动作才需要冻结凭据。"""
    context_actions = {a for a, p in JOB_IDENTITY_POLICY.items() if p == IDENTITY_CONTEXT}
    assert context_actions == {"participate", "participate_triple"}


def test_bound_action_without_account_uid_is_rejected(isolated_home: Path) -> None:
    """fail-closed：非 login action 缺 account_uid 直接拒绝启动。"""
    from src.db import init_db

    init_db()
    runner = JobRunner()
    with pytest.raises(ValueError, match="缺少 account_uid"):
        runner.try_start("refresh_status", {}, source="ui")
    assert runner.is_running() is False


def test_login_without_account_uid_is_allowed(isolated_home: Path, monkeypatch) -> None:
    """login 是唯一豁免：它的目的就是取得身份。"""
    from src.db import init_db
    from web import job_runner as jr

    init_db()
    runner = JobRunner()
    monkeypatch.setattr(jr, "run_action", lambda *a, **k: {"ok": True, "message": "ok"})
    job_id = runner.try_start("login", {}, source="ui")
    assert job_id is not None
