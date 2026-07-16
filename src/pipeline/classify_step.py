from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from src.bilibili_client import BilibiliClient
from src.forward_parser import classify_forward_lottery
from src.lottery_api import fetch_lottery_notice
from src.pipeline.classify_fetch_context import ClassifyFetchContext
from src.lottery_classifier import (
    LotteryType,
    UPOWER_BUSINESS_TYPE,
    _is_upower_lottery,
)
from src.sources.common import opus_link

SkipReason = Literal["链接失效", "充电抽奖", "非抽奖活动"]
ParticipatableType = Literal["互动抽奖", "预约抽奖", "转发抽奖"]


@dataclass(slots=True)
class ClassifyOutcome:
    dynamic_id: str
    lottery_type: LotteryType | Literal["非抽奖活动"] | None
    skipped: bool
    skip_reason: SkipReason | None = None
    classify_content: str = ""
    detail_item: dict[str, Any] | None = None
    lottery_notice: dict[str, Any] | None = None
    notice_business_type: int | None = None
    notice_business_id: str | None = None


def _classify_detail_item(ctx: ClassifyFetchContext) -> dict[str, Any] | None:
    return ctx.classify_detail_snapshot()


def _outcome_with_api_cache(
    outcome: ClassifyOutcome,
    ctx: ClassifyFetchContext,
    *,
    notice: dict[str, Any] | None = None,
    notice_business_type: int | None = None,
    notice_business_id: str | None = None,
) -> ClassifyOutcome:
    outcome.detail_item = _classify_detail_item(ctx)
    if notice and notice.get("lottery_id"):
        outcome.lottery_notice = notice
        outcome.notice_business_type = notice_business_type
        outcome.notice_business_id = notice_business_id
    return outcome


def classify_new_link(client: BilibiliClient, dynamic_id: str) -> ClassifyOutcome:
    """API 优先分类；其余由 LLM 判断是否为转发抽奖。skipped 不落库。"""
    ctx = ClassifyFetchContext(client, dynamic_id)
    referer = opus_link(dynamic_id)
    if ctx.is_deleted_link():
        return ClassifyOutcome(dynamic_id, None, True, "链接失效")

    additional = ctx.get_additional()
    if additional and _is_upower_lottery(additional):
        return ClassifyOutcome(dynamic_id, "充电抽奖", True, "充电抽奖")

    interact_notice = fetch_lottery_notice(
        client,
        business_id=dynamic_id,
        business_type=1,
        referer=referer,
        retries=1,
    )
    if interact_notice and interact_notice.get("lottery_id"):
        return _outcome_with_api_cache(
            ClassifyOutcome(dynamic_id, "互动抽奖", False),
            ctx,
            notice=interact_notice,
            notice_business_type=1,
            notice_business_id=dynamic_id,
        )

    upower_notice = fetch_lottery_notice(
        client,
        business_id=dynamic_id,
        business_type=UPOWER_BUSINESS_TYPE,
        referer=referer,
        retries=1,
    )
    if upower_notice and upower_notice.get("lottery_id"):
        return ClassifyOutcome(dynamic_id, "充电抽奖", True, "充电抽奖")

    reserve_outcome = ctx.classify_reserve_candidate(additional)
    if reserve_outcome == "skip":
        return ClassifyOutcome(dynamic_id, "非抽奖活动", True, "非抽奖活动")
    if reserve_outcome == "预约抽奖":
        reserve_bundle = ctx.resolve_reserve_lottery_notice()
        outcome = ClassifyOutcome(dynamic_id, "预约抽奖", False)
        if reserve_bundle:
            notice, business_id, business_type = reserve_bundle
            return _outcome_with_api_cache(
                outcome,
                ctx,
                notice=notice,
                notice_business_type=business_type,
                notice_business_id=business_id,
            )
        return _outcome_with_api_cache(outcome, ctx)

    content = ctx.resolve_classify_content()

    parsed = classify_forward_lottery(dynamic_id, content)
    if parsed.get("error"):
        raise RuntimeError(f"LLM 分类失败 {dynamic_id}: {parsed.get('error')}")

    if parsed.get("is_lottery"):
        return _outcome_with_api_cache(
            ClassifyOutcome(
                dynamic_id,
                "转发抽奖",
                False,
                classify_content=content,
            ),
            ctx,
        )
    return _outcome_with_api_cache(
        ClassifyOutcome(
            dynamic_id,
            "非抽奖活动",
            True,
            "非抽奖活动",
            classify_content=content,
        ),
        ctx,
    )
