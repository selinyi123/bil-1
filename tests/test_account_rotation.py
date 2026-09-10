"""多账号串行轮转（无状态）。

设计决定见 SPEC §6「多账号编排」与 `docs/15-账号隔离上下文-v1.md`：

- 串行，不并行——并行要拆掉「全机只有一个写者」这个不变量（§8 #7）；
- 无账号健康度/冷却——`AGENTS.md` 机制判据的「拒绝」列第一项就是账号级 FSM；
- 轮到谁**从时间槽派生**，不存游标：同一个槽 key 恒定映射到同一账号；
- 不切 active：按 uid 直接读 `accounts/{uid}.txt` 构建上下文，UI 身份不受后台任务影响。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.account_context import AccountContextUnavailable, capture_account_context_for_uid

UID_A = 4213
UID_B = 8888
COOKIE_TMPL = "DedeUserID={uid}; SESSDATA=s{uid}; bili_jct=jct{uid}"


def _write_account(home: Path, uid: int, cookie: str | None = None) -> None:
    accounts = home / "config" / "accounts"
    accounts.mkdir(parents=True, exist_ok=True)
    (accounts / f"{uid}.txt").write_text(
        cookie if cookie is not None else COOKIE_TMPL.format(uid=uid), encoding="utf-8"
    )


def test_capture_for_uid_reads_that_accounts_cookie(isolated_home: Path) -> None:
    """按 uid 取凭据，不依赖 cookies.txt（即当前 active 账号）。"""
    _write_account(isolated_home, UID_A)
    _write_account(isolated_home, UID_B)
    # 当前 active 是 A：轮到 B 时也必须拿到 B 的凭据
    (isolated_home / "config" / "cookies.txt").write_text(
        COOKIE_TMPL.format(uid=UID_A), encoding="utf-8"
    )

    ctx = capture_account_context_for_uid(UID_B)
    assert ctx.uid == UID_B
    assert ctx.csrf == f"jct{UID_B}"
    assert ctx.cookie_source == "account_pool"


def test_capture_for_uid_fails_closed_on_uid_mismatch(isolated_home: Path) -> None:
    """存的 cookie 解析出的 uid 与文件名不符时必须拒绝，不得拿错身份去请求。"""
    _write_account(isolated_home, UID_B, cookie=COOKIE_TMPL.format(uid=UID_A))
    with pytest.raises(AccountContextUnavailable):
        capture_account_context_for_uid(UID_B)


def test_capture_for_uid_fails_closed_when_account_missing(isolated_home: Path) -> None:
    with pytest.raises(AccountContextUnavailable):
        capture_account_context_for_uid(UID_B)


def test_capture_for_uid_fails_closed_on_incomplete_cookie(isolated_home: Path) -> None:
    """缺 bili_jct 就没有 CSRF，写动作必然失败——应在捕获阶段就拒绝。"""
    _write_account(isolated_home, UID_A, cookie=f"DedeUserID={UID_A}; SESSDATA=x")
    with pytest.raises(AccountContextUnavailable):
        capture_account_context_for_uid(UID_A)


def test_context_never_exposes_secrets_in_repr(isolated_home: Path) -> None:
    _write_account(isolated_home, UID_A)
    text = repr(capture_account_context_for_uid(UID_A))
    assert "SESSDATA" not in text and f"jct{UID_A}" not in text


# ---------------------------------------------------------------------------
# 轮转选号：从时间槽派生，不存游标
# ---------------------------------------------------------------------------

POOL = [111, 222, 333]


def test_same_slot_key_always_picks_the_same_account() -> None:
    """无状态的前提：不存游标，靠的是同一个槽恒定映射到同一账号。"""
    from web.auto_scheduler import rotation_uid_for_slot

    first = rotation_uid_for_slot("2026-09-10-14-05", POOL)
    for _ in range(5):
        assert rotation_uid_for_slot("2026-09-10-14-05", POOL) == first


def test_consecutive_slots_walk_the_pool() -> None:
    """连续三个刻度必须走遍三个账号，否则"轮转"名不副实。"""
    from web.auto_scheduler import rotation_uid_for_slot

    picked = [rotation_uid_for_slot(f"2026-09-10-14-{m:02d}", POOL) for m in (5, 10, 15)]
    assert sorted(picked) == sorted(POOL), picked


def test_single_account_pool_always_picks_it() -> None:
    from web.auto_scheduler import rotation_uid_for_slot

    assert rotation_uid_for_slot("2026-09-10-14-05", [111]) == 111


def test_empty_pool_yields_none() -> None:
    """池为空时返回 None，调用方回落到原有的生效身份，而不是崩掉调度器。"""
    from web.auto_scheduler import rotation_uid_for_slot

    assert rotation_uid_for_slot("2026-09-10-14-05", []) is None


def test_unparsable_slot_key_yields_none() -> None:
    from web.auto_scheduler import rotation_uid_for_slot

    assert rotation_uid_for_slot("not-a-slot", POOL) is None


# ---------------------------------------------------------------------------
# JobRunner：轮转任务绑定的不是活跃账号
# ---------------------------------------------------------------------------


def _wait_until(runner, predicate, timeout: float = 3.0) -> None:
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate(runner.get_status()):
            return
        time.sleep(0.05)
    raise AssertionError(f"timeout: {runner.get_status().to_dict()}")


def test_rotated_job_binds_the_rotated_account_not_the_active_one(isolated_home: Path) -> None:
    """轮转到 B 时，活跃账号仍是 A —— 身份校验必须放行，且上下文必须是 B 的。

    常规任务的 `resolve_effective_uid() == account_uid` 校验守的是"任务创建后
    活跃账号被切走"。轮转是**故意**绑定非活跃账号，保证由按 uid 取凭据本身
    提供（存的 cookie 解析出的 uid 必须等于请求 uid），不是靠这道校验。
    """
    from unittest.mock import patch

    from web.job_runner import JobRunner

    _write_account(isolated_home, UID_A)
    _write_account(isolated_home, UID_B)
    seen: dict[str, object] = {}

    def fake_run_action(action, params, *, on_progress, cancel_event, account_context=None):
        seen["uid"] = getattr(account_context, "uid", None)
        seen["source"] = getattr(account_context, "cookie_source", None)
        return {"ok": True, "message": "done"}

    runner = JobRunner()
    # 活跃账号是 A，轮转到 B
    with (
        patch("web.job_runner.resolve_effective_uid", return_value=UID_A),
        patch("web.job_runner.run_action", side_effect=fake_run_action),
    ):
        job_id = runner.try_start(
            "participate_triple", account_uid=str(UID_B), capture_uid=UID_B
        )
        assert job_id is not None
        _wait_until(runner, lambda s: s.state != "running")

    assert runner.get_status().state == "success", runner.get_status().to_dict()
    assert seen["uid"] == UID_B, "轮转任务拿到了错误账号的上下文"
    assert seen["source"] == "account_pool"


def test_non_rotated_job_still_enforces_active_identity(isolated_home: Path) -> None:
    """回归守卫：不传 capture_uid 时，原有的身份错配 fail-closed 不得被削弱。"""
    from unittest.mock import patch

    from web.job_runner import JobRunner

    from src.job_store import get_job

    _write_account(isolated_home, UID_A)
    runner = JobRunner()
    with (
        patch("web.job_runner.resolve_effective_uid", return_value=UID_A),
        patch("web.job_runner.run_action", side_effect=AssertionError("不得执行")),
    ):
        job_id = runner.try_start("participate_triple", account_uid=str(UID_B))
        _wait_until(runner, lambda s: s.state != "running")

    assert runner.get_status().state == "error"
    assert get_job(job_id)["error_kind"] == "identity"


# ---------------------------------------------------------------------------
# /api/auto/start 契约
# ---------------------------------------------------------------------------


def test_auto_start_defaults_to_no_rotation(isolated_home: Path) -> None:
    """默认关闭：不带 body 启动等价于 rotate_accounts=false（QH）。"""
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    from web.app import app

    with patch("web.app.auto_scheduler.start", return_value={"ok": True}) as start:
        assert TestClient(app).post("/api/auto/start").status_code == 200
    start.assert_called_once_with(rotate_accounts=False)


def test_auto_start_passes_rotation_flag(isolated_home: Path) -> None:
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    from web.app import app

    with patch("web.app.auto_scheduler.start", return_value={"ok": True}) as start:
        resp = TestClient(app).post("/api/auto/start", json={"rotate_accounts": True})
        assert resp.status_code == 200
    start.assert_called_once_with(rotate_accounts=True)


def test_auto_start_rejects_unknown_fields(isolated_home: Path) -> None:
    """extra=forbid：拼错的字段不得被静默吞掉，否则轮转会"看起来开了但没开"。"""
    from fastapi.testclient import TestClient

    from web.app import app

    resp = TestClient(app).post("/api/auto/start", json={"rotate_account": True})
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
