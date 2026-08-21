"""平台事实与其溯源必须原子持久化（PR-4 / review P1）。

背景：账号绑定的 preflight 会在内存里写入本账号观测到的平台事实，
随后 persist_activity_record 把这些账号态字段恢复成共享行的旧值，
以免污染其他账号。若恢复列表漏掉 platform_observed_uid，就会持久化出
「B 的事实 + A 的 observed_uid」——读侧据此认为那是 A 自己观测到的结果，
#6 建立的账号隔离被绕过。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.activity_store import load_activities, replace_all_activities
from src.status_refresh import persist_activity_record
from web.activity_service import _trusted_platform_facts

UID_A = "111"
UID_B = "222"
DYNAMIC_ID = "1220298825599549447"


def _shared_row(**overrides: object) -> dict:
    row = {
        "dynamic_id": DYNAMIC_ID,
        "lottery_type": "互动抽奖",
        "draw_status": "active",
        "lottery_time": 4102444800,
        "activity_status": "未参加",
        "status_classified": True,
        "prizes": [{"description": "奖", "winner_count": 1}],
    }
    row.update(overrides)
    return row


def _stored() -> dict:
    return next(item for item in load_activities() if item.get("dynamic_id") == DYNAMIC_ID)


def test_bound_preflight_does_not_relabel_other_accounts_fact(isolated_home: Path) -> None:
    """A 的绑定 preflight 不得把 B 的平台事实重新贴上 A 的 observed_uid。"""
    _ = isolated_home
    replace_all_activities([
        _shared_row(platform_participated=True, platform_observed_uid=UID_B)
    ])

    # A 实际观测到的是"未参与"，且溯源为 A
    item = _shared_row(platform_participated=False, platform_observed_uid=UID_A)
    persist_activity_record(item, participation=None, account_uid=UID_A)

    stored = _stored()
    assert stored["platform_participated"] is True, "共享行的事实被 A 覆盖了"
    assert stored["platform_observed_uid"] == UID_B, "事实是 B 的，溯源却被改成了 A"

    # 关键不变量：A 读这条共享行时不得采信 B 的事实
    participated, reserved = _trusted_platform_facts(stored, UID_A)
    assert participated is None and reserved is None


def test_bound_preflight_reserve_fact_keeps_its_provenance(isolated_home: Path) -> None:
    """预约字段遵循同一条规则。"""
    _ = isolated_home
    replace_all_activities([
        _shared_row(lottery_type="预约抽奖", reserve_reserved=True, platform_observed_uid=UID_B)
    ])

    item = _shared_row(lottery_type="预约抽奖", reserve_reserved=False, platform_observed_uid=UID_A)
    persist_activity_record(item, participation=None, account_uid=UID_A)

    stored = _stored()
    assert stored["reserve_reserved"] is True
    assert stored["platform_observed_uid"] == UID_B
    assert _trusted_platform_facts(stored, UID_A) == (None, None)


def test_legacy_unbound_path_still_persists_observed_uid(isolated_home: Path) -> None:
    """无 account_uid 的 legacy 路径照常写入事实与溯源（不受本次修复影响）。"""
    _ = isolated_home
    replace_all_activities([_shared_row()])

    item = _shared_row(platform_participated=True, platform_observed_uid=UID_A)
    persist_activity_record(item, participation=None)

    stored = _stored()
    assert stored["platform_participated"] is True
    assert stored["platform_observed_uid"] == UID_A
    assert _trusted_platform_facts(stored, UID_A) == (True, None)


def test_fact_and_provenance_are_restored_together(isolated_home: Path) -> None:
    """守住原则本身：三个字段必须同时出现在账号绑定的恢复列表里。"""
    _ = isolated_home
    from src.status_refresh import ACCOUNT_SCOPED_FIELDS, PLATFORM_FACT_FIELDS

    assert set(PLATFORM_FACT_FIELDS) <= set(ACCOUNT_SCOPED_FIELDS)
    assert "platform_observed_uid" in PLATFORM_FACT_FIELDS


def test_preflight_rejects_client_identity_mismatch(isolated_home: Path) -> None:
    """client 与 account_uid 是两个独立参数，写错会把 A 的观测标成 B 的。

    正常路径两者都来自同一个 AccountContext，但 API 层面这是 fail-open 的，
    因此显式断言一致性。
    """
    _ = isolated_home
    from src.participate_preflight import refresh_activity_status_from_live

    replace_all_activities([_shared_row()])

    class _ClientForA:
        login_uid = int(UID_A)

    with pytest.raises(RuntimeError, match="客户端身份与任务绑定账号不一致"):
        refresh_activity_status_from_live(
            _ClientForA(),  # type: ignore[arg-type]
            DYNAMIC_ID,
            lottery_type_hint="互动抽奖",
            account_uid=UID_B,
        )
