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

    ctx = capture_account_context_for_uid(expected_uid=UID_B)
    assert ctx.uid == UID_B
    assert ctx.csrf == f"jct{UID_B}"
    assert ctx.cookie_source == "account_pool"


def test_capture_for_uid_fails_closed_on_uid_mismatch(isolated_home: Path) -> None:
    """存的 cookie 解析出的 uid 与文件名不符时必须拒绝，不得拿错身份去请求。"""
    _write_account(isolated_home, UID_B, cookie=COOKIE_TMPL.format(uid=UID_A))
    with pytest.raises(AccountContextUnavailable):
        capture_account_context_for_uid(expected_uid=UID_B)


def test_capture_for_uid_fails_closed_when_account_missing(isolated_home: Path) -> None:
    with pytest.raises(AccountContextUnavailable):
        capture_account_context_for_uid(expected_uid=UID_B)


def test_capture_for_uid_fails_closed_on_incomplete_cookie(isolated_home: Path) -> None:
    """缺 bili_jct 就没有 CSRF，写动作必然失败——应在捕获阶段就拒绝。"""
    _write_account(isolated_home, UID_A, cookie=f"DedeUserID={UID_A}; SESSDATA=x")
    with pytest.raises(AccountContextUnavailable):
        capture_account_context_for_uid(expected_uid=UID_A)


def test_context_never_exposes_secrets_in_repr(isolated_home: Path) -> None:
    _write_account(isolated_home, UID_A)
    text = repr(capture_account_context_for_uid(expected_uid=UID_A))
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


def test_triple_slot_minutes_are_not_frozen_per_account() -> None:
    """每个号的动作时刻不得永久固定在同一组「分」上。

    `时*12` 里的 12 对 2/3/4/6/12 取模为 0，小时项整项消失——那些池规模下
    每个 uid 每天每小时都落在完全相同的分钟上，构成可长期观测的时刻签名。
    """
    from web.auto_scheduler import rotation_uid_for_slot

    minutes = list(range(5, 60, 5))
    for size in (2, 3, 4, 6, 12):
        pool = [100 + i for i in range(size)]
        patterns = {
            tuple(rotation_uid_for_slot(f"2026-09-{d}-{h:02d}-{m:02d}", pool) for m in minutes)
            for d in (10, 11)
            for h in (1, 2)
        }
        assert len(patterns) > 1, f"{size} 个账号时分钟分布恒定"


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


def test_rotation_precheck_targets_the_rotated_account(isolated_home: Path, monkeypatch) -> None:
    """登录前置校验必须查轮转到的号，不是活跃号。

    否则两个方向都坏：活跃号退登时池里健康的号每轮被 AUTH_REQUIRED 跳过；
    轮转号过期时活跃号照样通过校验，而按 uid 捕获只验 cookie 能否解析出
    uid/csrf（过期 cookie 这两样都在），于是每轮白烧一个刻度。
    """
    import web.auto_scheduler as sched

    seen: list[int | None] = []

    def fake_profile(uid: int | None = None, **_kw):
        seen.append(uid)
        return {"logged_in": True, "expired": False}

    monkeypatch.setattr(sched, "get_account_profile", fake_profile)
    monkeypatch.setattr(sched, "validate_job_prerequisites", lambda *a, **k: None, raising=False)

    scheduler = sched.AutoScheduler(job_runner=_StubRunner())
    # stub 的 try_start 返回 None，之后必然抛撞车——本例只关心前置校验查了谁
    with pytest.raises(sched.CollisionError):
        scheduler._click_and_wait("check_prize", rotate_to_uid=UID_B)

    assert seen == [UID_B], f"前置校验查的是 {seen}，应为 {[UID_B]}"


def test_done_keys_are_bounded() -> None:
    """已处理刻度集合必须有上限：key 按天递增、永不复用，长跑进程里无上限会一直涨。"""
    from web.auto_scheduler import _RecentKeys

    keys = _RecentKeys(maxlen=4)
    for i in range(10):
        keys.add(f"k{i}")
    assert len(keys) == 4
    assert "k9" in keys and "k0" not in keys
    keys.add("k9")  # 重复添加不占额度
    assert len(keys) == 4


def _scheduler_with_pool(monkeypatch, pool: list[int], proxies: dict[int, str] | None = None):
    import web.auto_scheduler as sched

    scheduler = sched.AutoScheduler(job_runner=_StubRunner())
    monkeypatch.setattr(scheduler, "_rotation_pool", lambda: pool)
    monkeypatch.setattr(
        "src.account_pool.get_account_proxy", lambda uid: (proxies or {}).get(uid)
    )
    return scheduler


def test_rotation_refused_when_pool_too_small(isolated_home: Path, monkeypatch) -> None:
    """SPEC §4.7 的「服务端可拒绝」之一，也是前端 toast 分支的依据。"""
    scheduler = _scheduler_with_pool(monkeypatch, [UID_A])
    assert scheduler.start(rotate_accounts=True)["rotate_accounts"] is False
    scheduler.stop()


def test_rotation_refused_when_env_cookie_overrides_identity(
    isolated_home: Path, monkeypatch
) -> None:
    """BILI_COOKIE 表达"所有请求都用这个身份"，与逐账号轮转互斥。

    这一支是唯一阻止轮转绕过 env 身份钉死的东西——`capture_account_context_for_uid`
    是**故意**不看 env 的，把这件事委托给调用方。
    """
    monkeypatch.setenv("BILI_COOKIE", "DedeUserID=1; bili_jct=x")
    scheduler = _scheduler_with_pool(monkeypatch, [UID_A, UID_B])
    assert scheduler.start(rotate_accounts=True)["rotate_accounts"] is False
    scheduler.stop()


def test_rotation_accepted_with_two_accounts(isolated_home: Path, monkeypatch) -> None:
    scheduler = _scheduler_with_pool(monkeypatch, [UID_A, UID_B])
    assert scheduler.start(rotate_accounts=True)["rotate_accounts"] is True
    scheduler.stop()


def test_shared_exit_ip_warns_but_does_not_block(isolated_home: Path, monkeypatch) -> None:
    """未配独立代理只警告不阻止——那是运维判断（QE=b）。"""
    scheduler = _scheduler_with_pool(monkeypatch, [UID_A, UID_B])
    status = scheduler.start(rotate_accounts=True)
    scheduler.stop()
    assert status["rotate_accounts"] is True
    logs = " ".join(item.get("message", "") for item in status.get("logs") or [])
    assert "未配置独立代理" in logs


def test_no_shared_ip_warning_when_each_account_has_a_proxy(
    isolated_home: Path, monkeypatch
) -> None:
    scheduler = _scheduler_with_pool(
        monkeypatch, [UID_A, UID_B], {UID_A: "http://a", UID_B: "http://b"}
    )
    status = scheduler.start(rotate_accounts=True)
    scheduler.stop()
    logs = " ".join(item.get("message", "") for item in status.get("logs") or [])
    assert "未配置独立代理" not in logs


def test_check_prize_slot_catches_up_after_a_long_batch(isolated_home: Path, monkeypatch) -> None:
    """批次跑过 :30 之后，深检刻度必须还能补跑，而不是被静默跳过。

    `_run_refresh_batch` 同步阻塞整个调度线程（三次 `_wait_until_terminal`，
    上限 6 小时）。原先用 `now.minute == 30` 精确匹配，批次跑到 :47 才返回时
    那一刻度根本不被求值——无日志、无撞车告警、`_done_check_prize` 里也不留痕。
    """
    from datetime import datetime

    import web.auto_scheduler as sched

    scheduler = sched.AutoScheduler(job_runner=_StubRunner())
    ran: list[str] = []
    monkeypatch.setattr(scheduler, "_run_check_prize_slot", lambda key: ran.append(key))

    # 整点小时，批次结束后已是 :47
    late = datetime(2026, 9, 10, 9, 47, tzinfo=sched.CN_TZ)
    assert scheduler._due_check_prize_key(late) is not None, "错过精确分钟后就补不上了"

    # 同一刻度只跑一次
    key = scheduler._due_check_prize_key(late)
    scheduler._done_check_prize.add(key)
    assert scheduler._due_check_prize_key(datetime(2026, 9, 10, 9, 55, tzinfo=sched.CN_TZ)) is None

    # :30 之前不该触发
    assert scheduler._due_check_prize_key(datetime(2026, 9, 10, 9, 12, tzinfo=sched.CN_TZ)) is None
    # 非整点小时不该触发
    assert scheduler._due_check_prize_key(datetime(2026, 9, 10, 10, 47, tzinfo=sched.CN_TZ)) is None


class _StubRunner:
    def is_running(self) -> bool:
        return False

    def get_status(self):
        class _S:
            def to_dict(self):
                return {}

        return _S()

    def try_start(self, *a, **k):
        return None


def test_auto_start_rejects_unknown_fields(isolated_home: Path) -> None:
    """extra=forbid：拼错的字段不得被静默吞掉，否则轮转会"看起来开了但没开"。"""
    from fastapi.testclient import TestClient

    from web.app import app

    resp = TestClient(app).post("/api/auto/start", json={"rotate_account": True})
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# check_prize：Context 化 + 整点轮转
# ---------------------------------------------------------------------------


def test_check_prize_is_context_bound() -> None:
    """升级为 context：凭据整任务冻结，否则轮转时它会按"当前 cookie"去查别人的私信。"""
    from web.job_runner import IDENTITY_CONTEXT, job_identity_policy

    assert job_identity_policy("check_prize") == IDENTITY_CONTEXT


def test_check_prize_uses_the_bound_context_client(isolated_home: Path) -> None:
    """深检必须用绑定上下文建客户端，不能用无参 BilibiliClient()（即当前 cookie）。"""
    from unittest.mock import patch

    from src.account_context import AccountContext
    from web.actions import run_action

    ctx = AccountContext(uid=UID_B, cookie="c", csrf="j", cookie_source="account_pool")
    seen: dict[str, object] = {}

    class FakeClient:
        def __init__(self, *, account_context=None, **kw):
            seen["ctx_uid"] = getattr(account_context, "uid", None)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    with (
        patch("web.actions.BilibiliClient", FakeClient),
        patch(
            "src.draw_check.check_prize_draw",
            return_value={"total": 0, "delivered": False, "acknowledged": False, "at": [], "reply": [], "dm": []},
        ),
    ):
        run_action("check_prize", {"push": False}, account_context=ctx)

    assert seen["ctx_uid"] == UID_B


def test_check_prize_slot_rotation_does_not_degenerate() -> None:
    """整点小时都是 3 的倍数，直接套三连的 `时*12` 会让 2/3/4 个账号恒定轮到同一个。"""
    from web.auto_config import REFRESH_HOURS
    from web.auto_scheduler import check_prize_uid_for_slot

    for size in (2, 3, 4):
        pool = [100 + i for i in range(size)]
        picked = [
            check_prize_uid_for_slot(f"2026-09-10-{h:02d}-30", pool)
            for h in sorted(REFRESH_HOURS)
        ]
        assert len(set(picked)) == size, f"{size} 个账号一天只轮到 {set(picked)}"


def test_check_prize_slot_is_deterministic() -> None:
    from web.auto_scheduler import check_prize_uid_for_slot

    key = "2026-09-10-09-30"
    first = check_prize_uid_for_slot(key, POOL)
    assert all(check_prize_uid_for_slot(key, POOL) == first for _ in range(5))


def test_check_prize_slot_shifts_across_days() -> None:
    """跨天必须换号，且**对每种池规模都成立**。

    第一版只用 3 个账号，恰好是会平移的那档；`yday * 8` 里的 8 对 2/4/8 取模为 0，
    当天序数整项消失，`00:30` 永远归 uid 最小的号。参数化才守得住。
    """
    from web.auto_scheduler import check_prize_uid_for_slot

    for size in (2, 3, 4, 5, 8):
        pool = [100 + i for i in range(size)]
        picked = [
            check_prize_uid_for_slot(f"2026-09-{d}-00-30", pool) for d in (10, 11, 12, 13)
        ]
        assert len(set(picked)) > 1, f"{size} 个账号时 00:30 恒定归 {picked[0]}"


def test_check_prize_daily_pattern_is_not_frozen() -> None:
    """整天的分布模式也不能逐日重复，否则每个号的深检时刻永久固定。"""
    from web.auto_config import REFRESH_HOURS
    from web.auto_scheduler import check_prize_uid_for_slot

    hours = sorted(REFRESH_HOURS)
    for size in (2, 3, 4, 5, 8):
        pool = [100 + i for i in range(size)]
        patterns = {
            tuple(check_prize_uid_for_slot(f"2026-09-{d}-{h:02d}-30", pool) for h in hours)
            for d in (10, 11, 12, 13)
        }
        assert len(patterns) > 1, f"{size} 个账号时四天分布完全相同"


def _enhance(monkeypatch, **overrides) -> None:
    from src.participate_enhance import DEFAULTS

    monkeypatch.setattr(
        "src.participate_enhance.load_participate_enhance",
        lambda: {**DEFAULTS, **overrides},
    )


def test_shared_enhance_fingerprint_warns_under_rotation(
    isolated_home: Path, monkeypatch
) -> None:
    """participate_enhance 是全局的：轮转换 cookie，不换话术指纹。

    同一批活动下 N 个账号 @ 同一群好友、带同一个话题标签，是比共用出口 IP
    更直接的关联信号。与出口 IP 那条同样只警告不阻止——per-account 配置是
    SPEC §6 记着的 gap，在它落地前，风险至少要出现在做决定的地方。
    """
    _enhance(monkeypatch, at_users=[{"uid": 1, "name": "甲"}], topic="抽奖")
    scheduler = _scheduler_with_pool(
        monkeypatch, [UID_A, UID_B], {UID_A: "http://a", UID_B: "http://b"}
    )
    status = scheduler.start(rotate_accounts=True)
    scheduler.stop()

    assert status["rotate_accounts"] is True
    logs = " ".join(item.get("message", "") for item in status.get("logs") or [])
    assert "@ 好友" in logs and "话题" in logs


def test_no_enhance_warning_when_nothing_is_shared(isolated_home: Path, monkeypatch) -> None:
    _enhance(monkeypatch)
    scheduler = _scheduler_with_pool(
        monkeypatch, [UID_A, UID_B], {UID_A: "http://a", UID_B: "http://b"}
    )
    status = scheduler.start(rotate_accounts=True)
    scheduler.stop()
    logs = " ".join(item.get("message", "") for item in status.get("logs") or [])
    assert "话术指纹" not in logs


def test_no_enhance_warning_without_rotation(isolated_home: Path, monkeypatch) -> None:
    """单账号下这些配置没有关联含义，不该噪声。"""
    _enhance(monkeypatch, at_users=[{"uid": 1, "name": "甲"}], topic="抽奖")
    scheduler = _scheduler_with_pool(monkeypatch, [UID_A, UID_B])
    status = scheduler.start()
    scheduler.stop()
    logs = " ".join(item.get("message", "") for item in status.get("logs") or [])
    assert "话术指纹" not in logs


def test_participate_uses_bound_context_client(isolated_home: Path) -> None:
    """单活动参与也必须用绑定上下文建客户端，理由与深检相同。

    `participate` 与 `check_prize` 同为 `context` 策略，但此前只有后者有接线测试。
    这条是 `test_context_actions_are_plumbed.py` 在第一次运行时逼出来的。
    """
    from unittest.mock import patch

    from src.account_context import AccountContext
    from web.actions import run_action

    ctx = AccountContext(uid=UID_B, cookie="c", csrf="j", cookie_source="account_pool")
    seen: list[int | None] = []

    class FakeClient:
        def __init__(self, *, account_context=None, **kw):
            seen.append(getattr(account_context, "uid", None))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class FakeResult:
        def to_dict(self) -> dict:
            return {
                "status": "joined",
                "message": "完成",
                "actions": [
                    {"action": name, "ok": True, "detail": ""}
                    for name in ("like", "follow", "favorite", "repost", "comment")
                ],
            }

    with (
        patch("web.actions.BilibiliClient", FakeClient),
        patch("web.actions.lookup_lottery_type", return_value="互动抽奖"),
        patch("web.actions.ensure_activity_participatable"),
        patch("web.actions.participate_activity", return_value=FakeResult()),
    ):
        payload = run_action(
            "participate",
            {"dynamic_id": "1220298825599549447"},
            on_progress=lambda **_: None,
            account_context=ctx,
        )

    assert payload["ok"] is True
    assert seen and all(uid == UID_B for uid in seen), seen
