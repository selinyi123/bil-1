"""三连候选必须按执行账号的台账筛选（SPEC §4.7）。

SPEC §4.7 写着「`pick_triple_participate_targets` 按 per-uid 的『未参加』筛选，
A 参与过不影响 B 的候选」。实现里写入端确实是 per-uid
（`participate_activity(account_uid=account_context.uid)` 落 `ParticipationRow(uid=B)`），
读取端却钉死在 `participation_uid()` → `get_active_uid()`。

隔离只封了写路径的一半，后果是双向的：

* 活跃号 A 参加过的活动，轮转到的 B **永远轮不到**；
* B 自己参加过的活动，下一槽再轮到 B 时仍显示「未参加」，**B 会重复参与**。

第二条是对平台可见的：同一账号在同一条动态上反复五连。
"""

from __future__ import annotations

from pathlib import Path

from src.activity_store import replace_all_activities
from src.db import init_db
from src.participation_store import set_participation_unlocked_for_uid
from web.activity_service import pick_triple_participate_targets

DYNAMIC_ID = "1220298825599549447"
FUTURE_LOTTERY_TIME = 4_100_000_000  # 2099 年，必定未开奖
UID_A = "111"
UID_B = "222"


def _open_activity() -> dict:
    return {
        "dynamic_id": DYNAMIC_ID,
        "lottery_type": "互动抽奖",
        "draw_status": "active",
        "activity_status": "未参加",
        "lottery_time": FUTURE_LOTTERY_TIME,
        "status_classified": True,
    }


def _ids(targets: list[dict]) -> list[str]:
    return [str(item.get("dynamic_id") or "") for item in targets]


def test_targets_exclude_what_the_executing_account_already_joined(isolated_home: Path) -> None:
    """B 参加过，以 B 的身份再选目标必须为空——否则 B 会重复参与同一条动态。"""
    init_db()
    replace_all_activities([_open_activity()])
    set_participation_unlocked_for_uid(DYNAMIC_ID, "已参加", uid=UID_B)

    assert _ids(pick_triple_participate_targets(viewer_uid=UID_B)) == []


def test_targets_ignore_another_accounts_ledger(isolated_home: Path) -> None:
    """B 参加过不影响 A 的候选——SPEC §4.7 的原话，反方向同样要成立。"""
    init_db()
    replace_all_activities([_open_activity()])
    set_participation_unlocked_for_uid(DYNAMIC_ID, "已参加", uid=UID_B)

    assert _ids(pick_triple_participate_targets(viewer_uid=UID_A)) == [DYNAMIC_ID]


def test_rotated_triple_picks_targets_as_the_bound_account() -> None:
    """竖切：轮转任务冻结了 B 的凭据，选目标也必须以 B 的身份筛。

    既有的三连测试全都 mock 掉 `pick_triple_participate_targets`，
    因此「用哪个号的台账选目标」这一段从来没有被任何测试覆盖过。
    """
    from unittest.mock import patch

    from src.account_context import AccountContext
    from web.actions import run_action

    ctx = AccountContext(uid=int(UID_B), cookie="c", csrf="j", cookie_source="account_pool")

    with patch("web.actions.pick_triple_participate_targets", return_value=[]) as picker:
        run_action("participate_triple", {}, on_progress=lambda **_: None, account_context=ctx)

    assert picker.call_args.kwargs.get("viewer_uid") == UID_B
