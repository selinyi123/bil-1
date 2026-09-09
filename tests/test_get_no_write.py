"""GET 路径不得写库（SPEC §8 不变量 #14）。

三类写入曾挂在读请求上：

1. `_load_activities_payload()` 调 `refresh_expired_activity_statuses()`，
   UPDATE 每条过期活动——**每次 GET 都可能写**；
2. `GET /api/watch-users` 调 `seed_from_candidates_if_empty()`；
3. `GET /api/accounts` 调 `ensure_legacy_account()`。

共同后果：HTTP GET 产生写副作用，且这些写入**不受写者锁仲裁**（见
`src/writer_lock.py` 与 SPEC §8 不变量 #7），可能与任务级写者并发改同一行。
1 改为读时派生；2、3 是首次运行引导，挪到 `_bootstrap_user_data()` 启动执行。

每个测试都先造出「旧代码会写」的前置状态——否则它守不住任何东西。
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import select

from src.activity_store import replace_all_activities
from src.db import init_db
from src.db.models import ActivityRow, WatchUserRow
from src.db.session import session_scope

PAST_LOTTERY_TIME = 1_600_000_000  # 2020-09-13，必定已过
DYNAMIC_ID = "1220298825599549447"

GET_PATHS = ("/api/summary", "/api/activities", "/api/activities/triple-targets")


def _expired_but_marked_active() -> dict:
    """开奖时间已过、但库里仍标着 active——正是旧代码会在 GET 里改写的那种行。"""
    return {
        "dynamic_id": DYNAMIC_ID,
        "lottery_type": "互动抽奖",
        "draw_status": "active",
        "activity_status": "未参加",
        "lottery_time": PAST_LOTTERY_TIME,
        "status_classified": True,
    }


def _stored_draw_status() -> str | None:
    with session_scope() as session:
        row = session.get(ActivityRow, DYNAMIC_ID)
        return None if row is None else row.draw_status


def test_get_endpoints_do_not_write_activity_rows(isolated_home: Path) -> None:
    init_db()
    replace_all_activities([_expired_but_marked_active()])
    assert _stored_draw_status() == "active"

    from web.app import app

    client = TestClient(app)
    for path in GET_PATHS:
        assert client.get(path).status_code == 200, path

    assert _stored_draw_status() == "active", "GET 路径改写了活动库"


def test_expired_activity_still_reads_as_ended(isolated_home: Path) -> None:
    """不写库不等于不生效：过期活动在响应里仍须是已结束。"""
    init_db()
    replace_all_activities([_expired_but_marked_active()])

    from web.app import app

    client = TestClient(app)
    payload = client.get("/api/activities").json()
    items = payload.get("activities") or payload.get("items") or []
    target = next((i for i in items if str(i.get("dynamic_id")) == DYNAMIC_ID), None)
    assert target is not None, f"响应里找不到活动：{payload}"
    assert target.get("draw_status") == "ended"
    assert target.get("activity_status") == "已结束"


def _watch_user_count() -> int:
    with session_scope() as session:
        return len(session.exec(select(WatchUserRow)).all())


def test_watch_users_get_does_not_seed(isolated_home: Path, monkeypatch) -> None:
    """前置：监控名单为空 + 候选文件存在——旧代码会在 GET 里灌入候选。"""
    import src.watch_users as watch_users

    init_db()
    candidates = isolated_home / "config" / "watch_users_candidates.json"
    candidates.write_text(
        json.dumps({"users": [{"mid": 4213, "name": "候选用户"}]}), encoding="utf-8"
    )
    monkeypatch.setattr(watch_users, "CANDIDATES_PATH", candidates)
    assert _watch_user_count() == 0

    from web.app import app

    assert TestClient(app).get("/api/watch-users").status_code == 200
    assert _watch_user_count() == 0, "GET /api/watch-users 灌入了候选名单"


def _legacy_cookie(home: Path) -> None:
    (home / "config" / "cookies.txt").write_text(
        "DedeUserID=4213; SESSDATA=x; bili_jct=y", encoding="utf-8"
    )


def test_accounts_get_does_not_adopt_legacy_cookie(isolated_home: Path) -> None:
    """前置：账号池为空 + cookies.txt 能解析出 uid——旧代码会在 GET 里收养它。"""
    from src.account_pool import list_accounts

    init_db()
    _legacy_cookie(isolated_home)
    assert list_accounts() == []

    from web.app import app

    assert TestClient(app).get("/api/accounts").status_code == 200
    assert list_accounts() == [], "GET /api/accounts 收养了遗留 cookie"


def test_proxy_settings_get_does_not_adopt_legacy_cookie(isolated_home: Path, monkeypatch) -> None:
    """GET /api/settings/proxy 走 `_require_local_account()`，那里也有收养写入。

    必须放行登录校验：否则 `require_login` 先抛错，测试会因为没走到收养那行而
    "通过"，证明不了任何事。
    """
    import web.product_routes as product_routes
    from src.account_pool import list_accounts

    init_db()
    _legacy_cookie(isolated_home)
    monkeypatch.setattr(product_routes, "require_login", lambda *a, **k: None)
    assert list_accounts() == []

    from web.app import app

    TestClient(app).get("/api/settings/proxy")
    assert list_accounts() == [], "GET /api/settings/proxy 收养了遗留 cookie"
