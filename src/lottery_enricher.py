from __future__ import annotations

import time
from dataclasses import asdict, dataclass, replace
from typing import Literal

from src.activity_status import ActivityStatus, StatusSource, resolve_activity_status
from src.bilibili_client import BilibiliClient
from src.forward_parser import MIN_CONTENT_LEN, fetch_dynamic_content, parse_forward_content
from src.lottery_api import (
    fetch_notice_for_interact,
    fetch_notice_for_reserve,
    fetch_reserve_button_status,
)
from src.lottery_classifier import LotteryType
from src.participation_store import ParticipationRecord
from src.sources.common import opus_link

DrawStatus = Literal["active", "ended"]
P1_LOTTERY_TYPES: tuple[LotteryType, ...] = ("互动抽奖", "预约抽奖")


@dataclass
class PrizeTier:
    tier: str
    winner_count: int
    description: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class WinnerEntry:
    uid: int
    name: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EnrichedActivity:
    dynamic_id: str
    source_url: str
    lottery_type: LotteryType
    enriched_at: int
    business_id: str
    business_type: int
    draw_status: DrawStatus
    lottery_time: int | None
    prizes: list[PrizeTier]
    participants: int
    conditions: dict[str, int | bool]
    winners: dict[str, list[WinnerEntry]] | None
    platform_participated: bool | None
    reserve_reserved: bool | None = None
    activity_status: ActivityStatus = "未参加"
    user_status_source: StatusSource = "default"
    lottery_detail_url: str = ""
    status_code: int | None = None
    skipped: bool = False
    skip_reason: str | None = None
    from_cache: bool = False

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["prizes"] = [item.to_dict() for item in self.prizes]
        if self.winners is not None:
            payload["winners"] = {
                tier: [entry.to_dict() for entry in entries]
                for tier, entries in self.winners.items()
            }
        return payload


def apply_p2_to_activity(
    activity: EnrichedActivity,
    participation: ParticipationRecord | None,
) -> EnrichedActivity:
    activity_status, source = resolve_activity_status(
        draw_status=activity.draw_status,
        lottery_type=activity.lottery_type,
        platform_participated=activity.platform_participated,
        reserve_reserved=activity.reserve_reserved,
        conditions=activity.conditions,
        participation=participation,
    )
    return replace(
        activity,
        activity_status=activity_status,
        user_status_source=source,
    )


def _parse_prizes(notice: dict) -> list[PrizeTier]:
    tiers: list[PrizeTier] = []
    mapping = (
        ("first", "first_prize", "first_prize_cmt"),
        ("second", "second_prize", "second_prize_cmt"),
        ("third", "third_prize", "third_prize_cmt"),
    )
    for tier, count_key, desc_key in mapping:
        count = int(notice.get(count_key) or 0)
        description = str(notice.get(desc_key) or "").strip()
        if count > 0 or description:
            tiers.append(PrizeTier(tier=tier, winner_count=count, description=description))
    return tiers


def _parse_winners(notice: dict) -> dict[str, list[WinnerEntry]] | None:
    result = notice.get("lottery_result") or {}
    if not result:
        return None
    winners: dict[str, list[WinnerEntry]] = {}
    for tier_key, entries in result.items():
        if not isinstance(entries, list) or not entries:
            continue
        tier_name = tier_key.replace("_prize_result", "")
        winners[tier_name] = [
            WinnerEntry(uid=int(item.get("uid") or 0), name=str(item.get("name") or ""))
            for item in entries
            if item.get("uid")
        ]
    return winners or None


def _resolve_draw_status(notice: dict) -> DrawStatus:
    status = int(notice.get("status") or 0)
    lottery_time = int(notice.get("lottery_time") or 0)
    if status != 0 or notice.get("lottery_result"):
        return "ended"
    if lottery_time and lottery_time <= int(time.time()):
        return "ended"
    return "active"


def _build_conditions(notice: dict) -> dict[str, int | bool]:
    return {
        "need_post": int(notice.get("need_post") or 0),
        "followed": bool(notice.get("followed")),
        "reposted": bool(notice.get("reposted")),
    }


def _build_from_notice(
    *,
    dynamic_id: str,
    lottery_type: LotteryType,
    notice: dict,
    business_type: int,
    business_id: str,
    from_cache: bool,
    reserve_reserved: bool | None = None,
    participation: ParticipationRecord | None = None,
) -> EnrichedActivity:
    activity = EnrichedActivity(
        dynamic_id=dynamic_id,
        source_url=opus_link(dynamic_id),
        lottery_type=lottery_type,
        enriched_at=int(time.time()),
        business_id=business_id,
        business_type=business_type,
        draw_status=_resolve_draw_status(notice),
        lottery_time=int(notice.get("lottery_time") or 0) or None,
        prizes=_parse_prizes(notice),
        participants=int(notice.get("participants") or 0),
        conditions=_build_conditions(notice),
        winners=_parse_winners(notice),
        platform_participated=bool(notice.get("participated")) if "participated" in notice else None,
        reserve_reserved=reserve_reserved,
        lottery_detail_url=str(notice.get("lottery_detail_url") or ""),
        status_code=int(notice.get("status") or 0),
        from_cache=from_cache,
    )
    return apply_p2_to_activity(activity, participation=participation)


def build_forward_stub(
    *,
    dynamic_id: str,
    lottery_type: LotteryType,
    participation: ParticipationRecord | None,
    skip_reason: str = "P3 解析失败",
) -> EnrichedActivity:
    activity = EnrichedActivity(
        dynamic_id=dynamic_id,
        source_url=opus_link(dynamic_id),
        lottery_type=lottery_type,
        enriched_at=int(time.time()),
        business_id=dynamic_id,
        business_type=0,
        draw_status="active",
        lottery_time=None,
        prizes=[],
        participants=0,
        conditions={},
        winners=None,
        platform_participated=None,
        reserve_reserved=None,
        skipped=True,
        skip_reason=skip_reason,
    )
    return apply_p2_to_activity(activity, participation=participation)


def enrich_forward_activity(
    client: BilibiliClient,
    *,
    dynamic_id: str,
    participation: ParticipationRecord | None = None,
) -> EnrichedActivity:
    content_text = fetch_dynamic_content(client, dynamic_id)
    if len(content_text.strip()) < MIN_CONTENT_LEN:
        return build_forward_stub(
            dynamic_id=dynamic_id,
            lottery_type="转发抽奖",
            participation=participation,
            skip_reason="无法提取动态正文（可能为纯图）",
        )

    try:
        parsed = parse_forward_content(dynamic_id, content_text)
    except Exception as exc:
        return build_forward_stub(
            dynamic_id=dynamic_id,
            lottery_type="转发抽奖",
            participation=participation,
            skip_reason=f"LLM 解析失败: {exc}",
        )

    if not parsed.get("is_lottery"):
        return build_forward_stub(
            dynamic_id=dynamic_id,
            lottery_type="转发抽奖",
            participation=participation,
            skip_reason=parsed.get("error") or "未识别为抽奖活动",
        )

    lottery_time_unix = parsed.get("lottery_time_unix")
    draw_status: DrawStatus = "active"
    if lottery_time_unix and int(lottery_time_unix) <= int(time.time()):
        draw_status = "ended"

    prize_description = str(parsed.get("prize_description") or "").strip()
    winner_count = int(parsed.get("winner_count") or 0)
    prizes: list[PrizeTier] = []
    if prize_description or winner_count > 0:
        prizes.append(
            PrizeTier(
                tier="first",
                winner_count=winner_count,
                description=prize_description,
            )
        )

    activity = EnrichedActivity(
        dynamic_id=dynamic_id,
        source_url=opus_link(dynamic_id),
        lottery_type="转发抽奖",
        enriched_at=int(time.time()),
        business_id=dynamic_id,
        business_type=0,
        draw_status=draw_status,
        lottery_time=int(lottery_time_unix) if lottery_time_unix else None,
        prizes=prizes,
        participants=0,
        conditions={
            "need_follow": bool(parsed.get("need_follow")),
            "need_repost": bool(parsed.get("need_repost")),
            "need_comment": bool(parsed.get("need_comment")),
            "lottery_time_text": str(parsed.get("lottery_time_text") or ""),
            "confidence": str(parsed.get("confidence") or "medium"),
            "parse_source": "llm_cache" if parsed.get("from_cache") else "llm",
            "winner_count": winner_count,
        },
        winners=None,
        platform_participated=None,
        reserve_reserved=None,
        skipped=False,
        skip_reason=None,
    )
    return apply_p2_to_activity(activity, participation=participation)


def enrich_activity(
    client: BilibiliClient,
    *,
    dynamic_id: str,
    lottery_type: LotteryType,
    participation: ParticipationRecord | None = None,
) -> EnrichedActivity:
    if lottery_type == "互动抽奖":
        resolved = fetch_notice_for_interact(client, dynamic_id)
    elif lottery_type == "预约抽奖":
        resolved = fetch_notice_for_reserve(client, dynamic_id)
    else:
        return enrich_forward_activity(client, dynamic_id=dynamic_id, participation=participation)

    if not resolved:
        activity = EnrichedActivity(
            dynamic_id=dynamic_id,
            source_url=opus_link(dynamic_id),
            lottery_type=lottery_type,
            enriched_at=int(time.time()),
            business_id=dynamic_id,
            business_type=0,
            draw_status="active",
            lottery_time=None,
            prizes=[],
            participants=0,
            conditions={},
            winners=None,
            platform_participated=None,
            reserve_reserved=None,
            skipped=True,
            skip_reason="未获取到 lottery_notice 数据",
        )
        return apply_p2_to_activity(activity, participation=participation)

    notice, business_type, business_id = resolved
    reserve_reserved = None
    if lottery_type == "预约抽奖":
        reserve_reserved = fetch_reserve_button_status(client, dynamic_id)

    return _build_from_notice(
        dynamic_id=dynamic_id,
        lottery_type=lottery_type,
        notice=notice,
        business_type=business_type,
        business_id=business_id,
        from_cache=False,
        reserve_reserved=reserve_reserved,
        participation=participation,
    )


def activity_from_cache(dynamic_id: str, lottery_type: LotteryType, cached: dict) -> EnrichedActivity | None:
    if cached.get("lottery_type") != lottery_type:
        return None
    try:
        prizes = [
            PrizeTier(
                tier=str(item.get("tier") or ""),
                winner_count=int(item.get("winner_count") or 0),
                description=str(item.get("description") or ""),
            )
            for item in cached.get("prizes") or []
        ]
        winners_raw = cached.get("winners")
        winners: dict[str, list[WinnerEntry]] | None = None
        if isinstance(winners_raw, dict):
            winners = {
                tier: [
                    WinnerEntry(uid=int(entry.get("uid") or 0), name=str(entry.get("name") or ""))
                    for entry in entries
                ]
                for tier, entries in winners_raw.items()
            }
        return EnrichedActivity(
            dynamic_id=dynamic_id,
            source_url=str(cached.get("source_url") or opus_link(dynamic_id)),
            lottery_type=lottery_type,
            enriched_at=int(cached.get("enriched_at") or 0),
            business_id=str(cached.get("business_id") or dynamic_id),
            business_type=int(cached.get("business_type") or 0),
            draw_status=cached.get("draw_status") or "active",
            lottery_time=cached.get("lottery_time"),
            prizes=prizes,
            participants=int(cached.get("participants") or 0),
            conditions=dict(cached.get("conditions") or {}),
            winners=winners,
            platform_participated=cached.get("platform_participated"),
            reserve_reserved=cached.get("reserve_reserved"),
            activity_status=cached.get("activity_status") or "未参加",
            user_status_source=cached.get("user_status_source") or "default",
            lottery_detail_url=str(cached.get("lottery_detail_url") or ""),
            status_code=cached.get("status_code"),
            skipped=bool(cached.get("skipped")),
            skip_reason=cached.get("skip_reason"),
            from_cache=True,
        )
    except (TypeError, ValueError):
        return None
