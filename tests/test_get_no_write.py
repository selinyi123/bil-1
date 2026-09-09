"""GET 路径不得写活动库（SPEC §8 不变量 #14）。

背景：`_load_activities_payload()` 曾在读请求里调用 `seed_activities_if_empty()`
与 `refresh_expired_activity_statuses()`，后者会 UPDATE 过期活动。两个后果：
GET 产生写副作用；这些写入**不受写者锁仲裁**（见 `src/writer_lock.py` 与
SPEC §8 不变量 #7），因此可能与任务级写者并发改同一行。

正确做法是让"已结束"成为读时派生状态：库里存什么不动，响应里算出来。
本测试同时守住两半——不写库，且仍然显示为已结束。
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from src.activity_store import replace_all_activities
from src.db import init_db
from src.db.models import ActivityRow
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
