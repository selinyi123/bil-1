"""按主键取活动类型（此前为全表加载 + 线性扫）。

`build_triple_progress_plan` 会对每个目标调用一次 `lookup_lottery_type`，
旧实现每次加载整张活动库，三连参与 3 个目标即 3 次全表加载。现有测试全部
mock 掉了它，真实实现此前零覆盖。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.activity_store import get_activity, replace_all_activities
from src.db import init_db
from web.activity_service import lookup_lottery_type

PARTICIPATABLE = "1220298825599549447"
CHARGING = "1220298825599549448"


def _activity(dynamic_id: str, lottery_type: str) -> dict:
    return {
        "dynamic_id": dynamic_id,
        "lottery_type": lottery_type,
        "draw_status": "active",
        "lottery_time": 4_102_444_800,  # 2100-01-01
    }


@pytest.fixture
def _library(isolated_home: Path) -> None:
    init_db()
    replace_all_activities(
        [_activity(PARTICIPATABLE, "互动抽奖"), _activity(CHARGING, "充电抽奖")]
    )


def test_returns_type_of_the_requested_activity(_library: None) -> None:
    assert lookup_lottery_type(PARTICIPATABLE) == "互动抽奖"


def test_unknown_id_raises(_library: None) -> None:
    with pytest.raises(RuntimeError):
        lookup_lottery_type("9999999999999999999")


def test_non_participatable_type_raises(_library: None) -> None:
    """充电抽奖可分类但不可参与，不能当作可参与类型返回。"""
    with pytest.raises(RuntimeError):
        lookup_lottery_type(CHARGING)


def test_get_activity_returns_none_for_missing_or_blank(_library: None) -> None:
    assert get_activity("9999999999999999999") is None
    assert get_activity("") is None
