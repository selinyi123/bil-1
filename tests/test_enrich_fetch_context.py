from __future__ import annotations

from src.lottery_enricher import EnrichedActivity, PrizeTier, enrich_activity
from src.pipeline.enrich_fetch_context import EnrichFetchContext


def test_enrich_context_reuses_single_detail_fetch(monkeypatch) -> None:
    calls = {"detail": 0}

    class _Client:
        pass

    raw_item = {
        "type": "DYNAMIC_TYPE_DRAW",
        "modules": {
            "module_stat": {"forward": {"count": 42}},
            "module_dynamic": {"major": {"type": "MAJOR_TYPE_DRAW"}},
        },
    }

    def fake_fetch_dynamic_detail(client, dynamic_id):
        calls["detail"] += 1
        return raw_item

    notice = {
        "lottery_id": 1,
        "first_prize": 1,
        "first_prize_cmt": "奖品A",
        "lottery_time": 9999999999,
        "participants": 10,
    }

    monkeypatch.setattr(
        "src.pipeline.enrich_fetch_context.fetch_dynamic_detail",
        fake_fetch_dynamic_detail,
    )
    monkeypatch.setattr(
        "src.lottery_enricher.fetch_notice_for_interact",
        lambda client, dynamic_id: (notice, 1, dynamic_id),
    )
    monkeypatch.setattr("src.lottery_enricher.is_upower_dynamic", lambda item: False)

    activity = enrich_activity(_Client(), dynamic_id="123", lottery_type="互动抽奖")
    assert activity.repost_count == 42
    assert calls["detail"] == 1


def test_enrich_context_reserve_reuses_detail_for_notice_status_and_heat(monkeypatch) -> None:
    calls = {"detail": 0}

    class _Client:
        pass

    raw_item = {
        "modules": {
            "module_stat": {"forward": {"count": 0}},
            "module_dynamic": {
                "additional": {
                    "reserve": {
                        "rid": 99,
                        "button": {"status": 2},
                    }
                }
            },
        }
    }

    def fake_fetch_dynamic_detail(client, dynamic_id):
        calls["detail"] += 1
        return raw_item

    notice = {
        "lottery_id": 1,
        "first_prize": 1,
        "first_prize_cmt": "预约奖",
        "lottery_time": 9999999999,
    }

    monkeypatch.setattr(
        "src.pipeline.enrich_fetch_context.fetch_dynamic_detail",
        fake_fetch_dynamic_detail,
    )
    monkeypatch.setattr("src.lottery_enricher.is_upower_dynamic", lambda item: False)
    monkeypatch.setattr(
        "src.lottery_enricher.fetch_notice_for_reserve",
        lambda client, dynamic_id, *, detail_item=None: (
            (notice, 10, "99") if detail_item is raw_item else None
        ),
    )
    monkeypatch.setattr(
        "src.lottery_enricher.fetch_reserve_button_status",
        lambda client, dynamic_id, *, detail_item=None: (
            True if detail_item is raw_item else None
        ),
    )

    activity = enrich_activity(_Client(), dynamic_id="123", lottery_type="预约抽奖")
    assert activity.reserve_reserved is True
    assert calls["detail"] == 1


def test_enrich_forward_uses_content_retry_and_reuses_detail(monkeypatch) -> None:
    calls = {"detail": 0, "content_retry": 0}

    class _Client:
        pass

    raw_item = {
        "type": "DYNAMIC_TYPE_FORWARD",
        "modules": {
            "module_stat": {"forward": {"count": 7}},
            "module_dynamic": {
                "desc": {"text": "转发抽奖正文足够长用于详情解析与缓存复用测试"},
            },
        },
    }

    def fake_fetch_dynamic_detail(client, dynamic_id):
        calls["detail"] += 1
        return raw_item

    def fake_content_retry(client, dynamic_id, *, initial_detail_item=None):
        calls["content_retry"] += 1
        assert initial_detail_item is raw_item
        return "转发抽奖正文足够长用于详情解析与缓存复用测试"

    parsed = {
        "parser_version": 4,
        "is_lottery": True,
        "prize_description": "礼包",
        "winner_count": 3,
        "lottery_time_unix": 9999999999,
        "lottery_time_text": "7月20日",
        "confidence": "high",
    }

    monkeypatch.setattr(
        "src.pipeline.enrich_fetch_context.fetch_dynamic_detail",
        fake_fetch_dynamic_detail,
    )
    monkeypatch.setattr(
        "src.lottery_enricher.fetch_dynamic_content_with_retry",
        fake_content_retry,
    )
    monkeypatch.setattr("src.lottery_enricher.parse_forward_content", lambda did, text: parsed)

    activity = enrich_activity(_Client(), dynamic_id="123", lottery_type="转发抽奖")
    assert activity.prizes[0].description == "礼包"
    assert activity.repost_count == 7
    assert calls["detail"] == 1
    assert calls["content_retry"] == 1


def test_enrich_interact_skips_notice_fetch_when_classify_cache_present(monkeypatch) -> None:
    calls = {"detail": 0, "notice": 0}

    class _Client:
        pass

    detail = {
        "modules": {
            "module_stat": {"forward": {"count": 12}},
        }
    }
    notice = {
        "lottery_id": 1,
        "first_prize": 1,
        "first_prize_cmt": "奖",
        "lottery_time": 9999999999,
    }

    monkeypatch.setattr(
        "src.pipeline.enrich_fetch_context.fetch_dynamic_detail",
        lambda *args, **kwargs: calls.__setitem__("detail", calls["detail"] + 1) or detail,
    )
    monkeypatch.setattr(
        "src.lottery_enricher.fetch_notice_for_interact",
        lambda *args, **kwargs: calls.__setitem__("notice", calls["notice"] + 1) or (notice, 1, "123"),
    )
    monkeypatch.setattr("src.lottery_enricher.is_upower_dynamic", lambda item: False)

    activity = enrich_activity(
        _Client(),
        dynamic_id="123",
        lottery_type="互动抽奖",
        classify_detail=detail,
        classify_notice=notice,
        classify_notice_business_type=1,
        classify_notice_business_id="123",
    )
    assert activity.repost_count == 12
    assert calls == {"detail": 0, "notice": 0}


def test_enrich_forward_reuses_classify_detail_without_refetch(monkeypatch) -> None:
    calls = {"content_retry": 0, "detail": 0}

    class _Client:
        pass

    parsed = {
        "parser_version": 6,
        "is_lottery": True,
        "prize_description": "礼包",
        "winner_count": 3,
        "lottery_time_unix": 9999999999,
        "lottery_time_text": "7月20日",
        "confidence": "high",
    }

    detail = {"modules": {"module_stat": {"forward": {"count": 2}}}}

    monkeypatch.setattr(
        "src.pipeline.enrich_fetch_context.fetch_dynamic_detail",
        lambda *args, **kwargs: calls.__setitem__("detail", calls["detail"] + 1) or detail,
    )
    monkeypatch.setattr(
        "src.lottery_enricher.fetch_dynamic_content_with_retry",
        lambda *args, **kwargs: calls.__setitem__("content_retry", calls["content_retry"] + 1) or "不应调用",
    )
    monkeypatch.setattr("src.lottery_enricher.parse_forward_content", lambda did, text: parsed)

    cached = "分类阶段已拉取的正文足够长用于详情解析复用测试"
    activity = enrich_activity(
        _Client(),
        dynamic_id="123",
        lottery_type="转发抽奖",
        classify_content=cached,
        classify_detail=detail,
    )
    assert activity.prizes[0].description == "礼包"
    assert activity.repost_count == 2
    assert calls["content_retry"] == 0
    assert calls["detail"] == 0


def test_attach_repost_count_refetches_when_initial_detail_missing(monkeypatch) -> None:
    calls = {"detail": 0}

    class _Client:
        pass

    item = {
        "modules": {
            "module_stat": {"forward": {"count": 5}},
        }
    }

    def fake_fetch_dynamic_detail(client, dynamic_id):
        calls["detail"] += 1
        return item if calls["detail"] == 2 else None

    monkeypatch.setattr(
        "src.pipeline.enrich_fetch_context.fetch_dynamic_detail",
        fake_fetch_dynamic_detail,
    )

    ctx = EnrichFetchContext(_Client(), "123")
    activity = EnrichedActivity(
        dynamic_id="123",
        source_url="https://example.com",
        lottery_type="互动抽奖",
        enriched_at=1,
        business_id="123",
        business_type=1,
        draw_status="active",
        lottery_time=9999999999,
        prizes=[PrizeTier(tier="first", winner_count=1, description="x")],
        participants=0,
        conditions={},
        winners=None,
        platform_participated=None,
    )
    updated = ctx.attach_repost_count(activity)
    assert updated.repost_count == 5
    assert calls["detail"] == 2
