from __future__ import annotations

from src.lottery_enricher import enrich_activity
from src.pipeline.refresh_all_pipeline import run_new_links_pipeline


def test_enrich_reuses_classify_detail_and_notice(monkeypatch) -> None:
    calls = {"detail": 0, "notice": 0}

    class _Client:
        pass

    detail = {
        "modules": {
            "module_stat": {"forward": {"count": 99}},
            "module_dynamic": {"major": {"type": "MAJOR_TYPE_DRAW"}},
        }
    }
    notice = {
        "lottery_id": 1,
        "first_prize": 1,
        "first_prize_cmt": "奖品",
        "lottery_time": 9999999999,
        "participants": 1,
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
    assert activity.repost_count == 99
    assert calls == {"detail": 0, "notice": 0}


def test_pipeline_passes_classify_api_cache_to_enrich(monkeypatch) -> None:
    captured: dict[str, object] = {}

    detail = {"modules": {"module_stat": {"forward": {"count": 3}}}}
    notice = {
        "lottery_id": 9,
        "first_prize": 1,
        "first_prize_cmt": "奖",
        "lottery_time": 9999999999,
    }

    def fake_classify(client, dynamic_id):
        from src.pipeline.classify_step import ClassifyOutcome

        return ClassifyOutcome(
            dynamic_id,
            "互动抽奖",
            False,
            detail_item=detail,
            lottery_notice=notice,
            notice_business_type=1,
            notice_business_id=dynamic_id,
        )

    def fake_enrich(client, **kwargs):
        captured.update(kwargs)
        from src.lottery_enricher import EnrichedActivity, PrizeTier

        return EnrichedActivity(
            dynamic_id=kwargs["dynamic_id"],
            source_url=f"https://www.bilibili.com/opus/{kwargs['dynamic_id']}",
            lottery_type="互动抽奖",
            enriched_at=1,
            business_id=kwargs["dynamic_id"],
            business_type=1,
            draw_status="active",
            lottery_time=9999999999,
            prizes=[PrizeTier(tier="first", winner_count=1, description="奖")],
            participants=0,
            conditions={},
            winners=None,
            platform_participated=None,
            repost_count=3,
            repost_fetched=True,
        )

    client_instances: list[object] = []

    class _TrackingClient:
        def __init__(self, *args, **kwargs):
            client_instances.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.known_activity_ids", lambda: set())
    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.classify_new_link", fake_classify)
    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.load_participations", lambda: {})
    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.enrich_activity", fake_enrich)
    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.BilibiliClient", _TrackingClient)
    monkeypatch.setattr(
        "src.pipeline.refresh_all_pipeline.apply_initial_status",
        lambda row: row,
    )
    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.append_activities", lambda rows: len(rows))

    run_new_links_pipeline(
        ["https://www.bilibili.com/opus/1224962472871460886"],
        workers=2,
    )

    assert captured["classify_detail"] is detail
    assert captured["classify_notice"] is notice
    assert captured["classify_notice_business_type"] == 1
    assert captured["classify_notice_business_id"] == "1224962472871460886"
    assert len(client_instances) == 2
