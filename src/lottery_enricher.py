from __future__ import annotations

import time
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from typing import Literal

from src.activity_status import ActivityStatus, StatusSource, resolve_activity_status
from src.bilibili_client import BilibiliClient
from src.forward_parser import (
    MIN_CONTENT_LEN,
    fetch_dynamic_content_with_retry,
    parse_forward_content,
)
from src.lottery_api import (
    fetch_notice_for_interact,
    fetch_notice_for_reserve,
    fetch_reserve_button_status,
    is_upower_dynamic,
)
from src.lottery_classifier import LotteryType, UPOWER_BUSINESS_TYPE
from src.lottery_time import (
    BEIJING_TZ,
    LOTTERY_TIME_DISPLAY_FMT,
    default_lottery_time_from_now,
    format_timestamp,
    is_standard_lottery_time_display,
    migrate_lottery_time_fields,
)
from src.participation_store import ParticipationRecord
from src.sources.common import opus_link

DrawStatus = Literal["active", "ended"]
P1_LOTTERY_TYPES: tuple[LotteryType, ...] = ("互动抽奖", "预约抽奖")
ENRICH_SKIP_REASON = "详情提取失败"
ENRICH_SKIP_RUNTIME_MARKERS = (
    "未识别为抽奖活动",
    "LLM 未解析出奖品",
)


class EnrichSkippedError(Exception):
    """详情阶段 LLM/结构化提取失败：跳过该链接，不落库。"""

    def __init__(self, dynamic_id: str, *, reason: str = ENRICH_SKIP_REASON) -> None:
        self.dynamic_id = dynamic_id
        self.reason = reason
        super().__init__(f"{reason}: {dynamic_id}")


def is_enrich_detail_skip_error(exc: BaseException) -> bool:
    if isinstance(exc, EnrichSkippedError):
        return True
    if isinstance(exc, RuntimeError):
        message = str(exc)
        return any(marker in message for marker in ENRICH_SKIP_RUNTIME_MARKERS)
    return False


def _lottery_time_from_llm_parse(parsed: dict) -> tuple[int, dict[str, int | bool | str]]:
    """转发抽奖：只接受 LLM 的 YYYY-MM-DD HH:mm（北京时间），再转为 Unix 入库。"""
    conditions: dict[str, int | bool | str] = {}
    display = str(parsed.get("lottery_time") or "").strip()
    if is_standard_lottery_time_display(display):
        conditions["lottery_time_text"] = display
        unix = int(
            datetime.strptime(display, LOTTERY_TIME_DISPLAY_FMT)
            .replace(tzinfo=BEIJING_TZ)
            .timestamp()
        )
        return unix, conditions

    inferred = default_lottery_time_from_now()
    conditions["lottery_time_inferred"] = True
    conditions["lottery_time_text"] = format_timestamp(inferred)
    return inferred, conditions


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
    repost_count: int = 0
    repost_fetched: bool = False
    repost_zero_confirmed: bool = False
    heat_from_reserve: bool = False
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


def normalize_enriched_lottery_time(activity: EnrichedActivity) -> EnrichedActivity:
    """将活动开奖时间字段规范为统一存储格式。"""
    payload = activity.to_dict()
    migrate_lottery_time_fields(payload)
    return replace(
        activity,
        lottery_time=payload.get("lottery_time"),
        conditions=dict(payload.get("conditions") or {}),
    )


def _apply_default_lottery_time(activity: EnrichedActivity) -> EnrichedActivity:
    if activity.lottery_time:
        return activity
    inferred_ts = default_lottery_time_from_now()
    conditions = dict(activity.conditions)
    conditions["lottery_time_text"] = format_timestamp(inferred_ts)
    conditions["lottery_time_inferred"] = True
    return replace(activity, lottery_time=inferred_ts, conditions=conditions)


def _validate_enriched(activity: EnrichedActivity) -> EnrichedActivity:
    if activity.skipped:
        if activity.lottery_type == "充电抽奖":
            return activity
        raise RuntimeError(
            f"活动 {activity.dynamic_id} 被标记为 skipped，仅允许充电抽奖: {activity.skip_reason}"
        )
    if not activity.repost_fetched:
        raise RuntimeError(f"活动 {activity.dynamic_id} 缺少热度数据")
    if activity.lottery_time is None:
        activity = _apply_default_lottery_time(activity)
    if not activity.prizes:
        raise RuntimeError(f"活动 {activity.dynamic_id} 缺少奖品信息")
    return activity


def build_skipped_charging(
    *,
    dynamic_id: str,
    participation: ParticipationRecord | None = None,
) -> EnrichedActivity:
    activity = EnrichedActivity(
        dynamic_id=dynamic_id,
        source_url=opus_link(dynamic_id),
        lottery_type="充电抽奖",
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
        skip_reason="充电专属抽奖，不参与",
    )
    return apply_p2_to_activity(activity, participation=participation)


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


def enrich_forward_activity(
    client: BilibiliClient,
    *,
    dynamic_id: str,
    participation: ParticipationRecord | None = None,
    classify_content: str | None = None,
    classify_detail: dict | None = None,
) -> EnrichedActivity:
    from src.pipeline.enrich_fetch_context import EnrichFetchContext

    ctx = EnrichFetchContext(client, dynamic_id, preloaded_detail=classify_detail)
    detail_item = ctx.get_detail_item()
    cached_content = str(classify_content or "").strip()
    if cached_content:
        content_text = cached_content
    else:
        content_text = fetch_dynamic_content_with_retry(
            client,
            dynamic_id,
            initial_detail_item=detail_item,
        )
    if len(content_text.strip()) < MIN_CONTENT_LEN:
        raise RuntimeError(f"无法提取动态正文（可能为纯图）: {dynamic_id}")

    parsed = parse_forward_content(dynamic_id, content_text)
    if parsed.get("error"):
        raise EnrichSkippedError(dynamic_id)
    if not parsed.get("is_lottery"):
        raise EnrichSkippedError(dynamic_id)

    lottery_ts, conditions = _lottery_time_from_llm_parse(parsed)
    draw_status: DrawStatus = "active"

    prize_description = str(parsed.get("prize_description") or "").strip()
    winner_count = int(parsed.get("winner_count") or 0)
    if not prize_description:
        raise EnrichSkippedError(dynamic_id)

    prizes = [
        PrizeTier(
            tier="first",
            winner_count=winner_count,
            description=prize_description,
        )
    ]

    activity = EnrichedActivity(
        dynamic_id=dynamic_id,
        source_url=opus_link(dynamic_id),
        lottery_type="转发抽奖",
        enriched_at=int(time.time()),
        business_id=dynamic_id,
        business_type=0,
        draw_status=draw_status,
        lottery_time=int(lottery_ts),
        prizes=prizes,
        participants=0,
        conditions=conditions,
        winners=None,
        platform_participated=None,
        reserve_reserved=None,
        skipped=False,
        skip_reason=None,
    )
    activity = apply_p2_to_activity(activity, participation=participation)
    return _validate_enriched(
        normalize_enriched_lottery_time(ctx.attach_repost_count(activity))
    )


def enrich_activity(
    client: BilibiliClient,
    *,
    dynamic_id: str,
    lottery_type: LotteryType,
    participation: ParticipationRecord | None = None,
    classify_content: str | None = None,
    classify_detail: dict | None = None,
    classify_notice: dict | None = None,
    classify_notice_business_type: int | None = None,
    classify_notice_business_id: str | None = None,
) -> EnrichedActivity:
    if lottery_type == "充电抽奖":
        return build_skipped_charging(dynamic_id=dynamic_id, participation=participation)
    if lottery_type == "转发抽奖":
        return enrich_forward_activity(
            client,
            dynamic_id=dynamic_id,
            participation=participation,
            classify_content=classify_content,
            classify_detail=classify_detail,
        )

    from src.pipeline.enrich_fetch_context import EnrichFetchContext

    ctx = EnrichFetchContext(client, dynamic_id, preloaded_detail=classify_detail)
    detail_item = ctx.get_detail_item()
    if is_upower_dynamic(detail_item):
        return build_skipped_charging(dynamic_id=dynamic_id, participation=participation)

    resolved: tuple[dict, int, str] | None = None
    if (
        classify_notice
        and classify_notice.get("lottery_id")
        and classify_notice_business_type is not None
        and classify_notice_business_id
    ):
        resolved = (classify_notice, classify_notice_business_type, classify_notice_business_id)
    elif lottery_type == "互动抽奖":
        resolved = fetch_notice_for_interact(client, dynamic_id)
    elif lottery_type == "预约抽奖":
        resolved = fetch_notice_for_reserve(client, dynamic_id, detail_item=detail_item)
    else:
        raise RuntimeError(f"不支持的抽奖类型: {lottery_type}")

    if not resolved:
        raise RuntimeError(f"未获取到 lottery_notice 数据: {dynamic_id}")

    notice, business_type, business_id = resolved
    if business_type == UPOWER_BUSINESS_TYPE:
        return build_skipped_charging(dynamic_id=dynamic_id, participation=participation)

    reserve_reserved = None
    if lottery_type == "预约抽奖":
        reserve_reserved = fetch_reserve_button_status(
            client,
            dynamic_id,
            detail_item=detail_item,
        )

    activity = _build_from_notice(
        dynamic_id=dynamic_id,
        lottery_type=lottery_type,
        notice=notice,
        business_type=business_type,
        business_id=business_id,
        from_cache=False,
        reserve_reserved=reserve_reserved,
        participation=participation,
    )
    activity = _apply_default_lottery_time(activity)
    if not activity.prizes:
        raise RuntimeError(f"未获取到奖品信息: {dynamic_id}")
    return _validate_enriched(ctx.attach_repost_count(activity))


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
        return normalize_enriched_lottery_time(
            EnrichedActivity(
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
                repost_count=int(cached.get("repost_count") or 0),
                repost_fetched=bool(cached.get("repost_fetched")),
                repost_zero_confirmed=bool(cached.get("repost_zero_confirmed")),
                heat_from_reserve=bool(cached.get("heat_from_reserve")),
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
        )
    except (TypeError, ValueError):
        return None
