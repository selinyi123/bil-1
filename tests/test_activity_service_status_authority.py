"""共享 ActivityRow 不再是账号状态权威（PR-2 / Q14）。

背景：apply_initial_status 对每条新入库活动恒置 status_classified=True，
participation.py 在参与成功后又把 activity_status="已参加" 写回同一条共享行。
读侧原本在 per-UID resolver 之前直接返回该共享字段，于是：
  - 账号 A 参与过 → 账号 B 也显示"已参加"（跨账号污染）
  - platform_participated / reserve_reserved 永远不被读取（死输入）
"""

from __future__ import annotations

from src.participation_store import ParticipationRecord
from web.activity_service import _resolve_activity_status


def _joined(dynamic_id: str = "1220298825599549447") -> ParticipationRecord:
    return ParticipationRecord(dynamic_id=dynamic_id, user_status="已参加", updated_at=1)


UID_A = "111"
UID_B = "222"


def _base(**overrides: object) -> dict:
    item = {
        "dynamic_id": "1220298825599549447",
        "lottery_type": "互动抽奖",
        "draw_status": "active",
        "lottery_time": 4102444800,  # 2100-01-01，确保不被"已结束"分支拦截
        "status_classified": True,
    }
    item.update(overrides)
    return item


def test_shared_joined_does_not_leak_to_account_without_record() -> None:
    """账号 A 参与后写进共享行的"已参加"，不得被没有参与记录的账号 B 继承。"""
    item = _base(activity_status="已参加", platform_participated=False, platform_observed_uid=UID_A)
    assert _resolve_activity_status(item, None, viewer_uid=UID_A) == "未参加"


def test_per_uid_record_wins_over_shared_unjoined() -> None:
    """共享行说"未参加"，但当前账号有参与记录时，以账号记录为准。"""
    item = _base(activity_status="未参加", platform_participated=False, platform_observed_uid=UID_A)
    assert _resolve_activity_status(item, _joined(), viewer_uid=UID_A) == "已参加"


def test_platform_fact_is_read_when_observed_by_same_account() -> None:
    """早退移除后，**本账号观测到的**平台事实重新生效（此前是死输入）。"""
    item = _base(
        activity_status="未参加", platform_participated=True, platform_observed_uid=UID_A
    )
    assert _resolve_activity_status(item, None, viewer_uid=UID_A) == "已参加"


def test_platform_fact_from_another_account_is_not_trusted() -> None:
    """账号 A enrich 出的"已参与"不得让账号 B 显示已参加。

    platform_participated 来自 notice.participated（带登录态），
    reserve_reserved 来自 fetch_reserve_button_status（带登录态），
    两者都是账号态事实却存在共享行——与 activity_status 是同一类污染，只是低一层。
    """
    item = _base(
        activity_status="未参加", platform_participated=True, platform_observed_uid=UID_A
    )
    assert _resolve_activity_status(item, None, viewer_uid=UID_B) == "未参加"


def test_legacy_row_without_provenance_is_not_trusted() -> None:
    """遗留数据没有观测账号，一律不信任（fail-closed）。"""
    item = _base(activity_status="未参加", platform_participated=True)
    assert _resolve_activity_status(item, None, viewer_uid=UID_A) == "未参加"


def test_reserve_reserved_follows_the_same_provenance_rule() -> None:
    same = _base(
        lottery_type="预约抽奖",
        activity_status="未参加",
        reserve_reserved=True,
        platform_observed_uid=UID_A,
    )
    assert _resolve_activity_status(same, None, viewer_uid=UID_A) == "已参加"
    assert _resolve_activity_status(same, None, viewer_uid=UID_B) == "未参加"

    legacy = _base(lottery_type="预约抽奖", activity_status="未参加", reserve_reserved=True)
    assert _resolve_activity_status(legacy, None, viewer_uid=UID_A) == "未参加"


def test_own_participation_record_wins_regardless_of_provenance() -> None:
    """本账号有参与记录时，不受平台事实溯源影响。"""
    item = _base(
        activity_status="未参加", platform_participated=True, platform_observed_uid=UID_A
    )
    assert _resolve_activity_status(item, _joined(), viewer_uid=UID_B) == "已参加"


def test_forward_lottery_still_defaults_unjoined() -> None:
    """转发抽奖无平台侧事实可查，共享行的"已参加"同样不得泄漏。"""
    item = _base(
        lottery_type="转发抽奖",
        activity_status="已参加",
        platform_participated=True,
        platform_observed_uid=UID_A,
    )
    assert _resolve_activity_status(item, None, viewer_uid=UID_A) == "未参加"
    assert _resolve_activity_status(item, _joined(), viewer_uid=UID_A) == "已参加"


def test_non_participatable_type_still_falls_back_to_shared_field() -> None:
    """不可参与类型（付费/充电）没有 per-UID 语义，仍回落共享字段。"""
    item = _base(lottery_type="付费抽奖", activity_status="已结束")
    assert _resolve_activity_status(item, None, viewer_uid=UID_A) == "已结束"

    charging = _base(lottery_type="充电抽奖", activity_status="已跳过")
    assert _resolve_activity_status(charging, None, viewer_uid=UID_A) == "已跳过"


def test_past_end_still_wins_over_everything() -> None:
    item = _base(
        activity_status="未参加",
        lottery_time=1,
        platform_participated=True,
        platform_observed_uid=UID_A,
    )
    assert _resolve_activity_status(item, _joined(), viewer_uid=UID_A) == "已结束"
