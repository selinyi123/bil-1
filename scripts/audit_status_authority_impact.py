#!/usr/bin/env python3
"""只读统计：移除 status_classified 早退后，有多少活动的展示状态会改变。

背景见 PR-2 / docs/14。移除早退后，可参与活动一律走 resolve_activity_status()，
`platform_participated` / `reserve_reserved` 这两个此前从未被读取的字段重新生效。
本脚本对比新旧两套判定，报告差异规模，用来决定这次变更是
「顺手激活一个死输入」还是「需要单独说明的状态迁移」。

严格只读：直接查 ActivityRow，不经 load_payload()（后者会触发过期状态回写）。

    python scripts/audit_status_authority_impact.py [--samples 10]
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import select  # noqa: E402

from src.activity_status import resolve_activity_status  # noqa: E402
from src.db.activity_codec import row_to_activity_dict  # noqa: E402
from src.db.models import ActivityRow  # noqa: E402
from src.db.session import session_scope  # noqa: E402
from src.lottery_classifier import PARTICIPATABLE_TYPES, is_charging_lottery_activity  # noqa: E402
from src.lottery_time import is_activity_past_end  # noqa: E402
from src.participation_store import ParticipationRecord, load_participations  # noqa: E402


def _status_old(item: dict, participation: ParticipationRecord | None) -> str:
    """移除前的判定（含 status_classified 早退）。"""
    if is_charging_lottery_activity(item):
        return str(item.get("activity_status") or "未参加")
    if is_activity_past_end(item, participation):
        return "已结束"
    if item.get("status_classified") and item.get("activity_status"):
        return str(item.get("activity_status"))
    return _status_new(item, participation)


def _status_new(item: dict, participation: ParticipationRecord | None) -> str:
    """移除后的判定。"""
    if is_charging_lottery_activity(item):
        return str(item.get("activity_status") or "未参加")
    if is_activity_past_end(item, participation):
        return "已结束"
    lottery_type = item.get("lottery_type")
    if lottery_type not in PARTICIPATABLE_TYPES:
        return str(item.get("activity_status") or "未参加")
    status, _ = resolve_activity_status(
        draw_status=item.get("draw_status") or "active",
        lottery_type=lottery_type,
        platform_participated=item.get("platform_participated"),
        reserve_reserved=item.get("reserve_reserved"),
        conditions=item.get("conditions") or {},
        participation=participation,
    )
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=10, help="每种迁移打印的样本条数")
    args = parser.parse_args()

    participations = load_participations()
    with session_scope() as session:
        rows = list(session.exec(select(ActivityRow)))
        items = [row_to_activity_dict(row) for row in rows]

    total = len(items)
    transitions: Counter[str] = Counter()
    by_type: Counter[str] = Counter()
    samples: dict[str, list[str]] = {}

    for item in items:
        dynamic_id = str(item.get("dynamic_id") or "")
        participation = participations.get(dynamic_id)
        old = _status_old(item, participation)
        new = _status_new(item, participation)
        if old == new:
            continue
        key = f"{old} → {new}"
        transitions[key] += 1
        by_type[f"{key} · {item.get('lottery_type') or '未知类型'}"] += 1
        samples.setdefault(key, [])
        if len(samples[key]) < args.samples:
            samples[key].append(dynamic_id)

    changed = sum(transitions.values())
    print(f"活动总数：{total}")
    print(f"当前账号参与记录数：{len(participations)}")
    print(f"展示状态会改变的活动数：{changed}" + (f"（{changed / total:.1%}）" if total else ""))

    if not changed:
        print("\n结论：没有活动的展示状态改变——本次变更是纯粹激活死输入，无需单独说明。")
        return 0

    print("\n按迁移方向：")
    for key, count in transitions.most_common():
        print(f"  {key}: {count}")
    print("\n按迁移方向 × 抽奖类型：")
    for key, count in by_type.most_common():
        print(f"  {key}: {count}")
    print("\n样本 dynamic_id：")
    for key, ids in samples.items():
        print(f"  {key}: {', '.join(ids)}")
    print(
        "\n提示：「未参加 → 已参加」表示平台侧显示该账号已参与但本地无参与记录。"
        "\n这类活动此后不再进入三连候选池，属于预期收益（避免重复参与）。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
