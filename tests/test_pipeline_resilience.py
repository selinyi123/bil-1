"""流水线容错回归测试：单条动态分类/详情失败不得阻塞其余动态入库。"""
from __future__ import annotations

from src.pipeline.refresh_all_pipeline import (
    CLASSIFY_FAILED_REASON,
    ENRICH_FAILED_REASON,
    run_new_links_pipeline,
)

_OK_ID = "1224962472871460886"
_BAD_ID = "1224962472871460885"


def _ok_activity(dynamic_id: str):
    from src.lottery_enricher import EnrichedActivity, PrizeTier

    return EnrichedActivity(
        dynamic_id=dynamic_id,
        source_url=f"https://www.bilibili.com/opus/{dynamic_id}",
        lottery_type="转发抽奖",
        enriched_at=1,
        business_id=dynamic_id,
        business_type=0,
        draw_status="active",
        lottery_time=9999999999,
        prizes=[PrizeTier(tier="first", winner_count=1, description="奖")],
        participants=0,
        conditions={},
        winners=None,
        platform_participated=None,
        repost_count=1,
        repost_fetched=True,
    )


def _patch_pipeline(monkeypatch, *, classify, enrich) -> list[dict]:
    saved: list[dict] = []
    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.known_activity_ids", lambda: set())
    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.classify_new_link", classify)
    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.load_participations", lambda: {})
    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.enrich_activity", enrich)
    monkeypatch.setattr(
        "src.pipeline.refresh_all_pipeline.apply_initial_status",
        lambda row: row,
    )
    monkeypatch.setattr(
        "src.pipeline.refresh_all_pipeline.append_activities",
        lambda rows: saved.extend(rows) or len(rows),
    )
    return saved


def test_pipeline_continues_when_classify_fails(monkeypatch) -> None:
    from src.pipeline.classify_step import ClassifyOutcome

    def fake_classify(client, dynamic_id):
        if dynamic_id == _BAD_ID:
            raise RuntimeError("网络超时")
        return ClassifyOutcome(dynamic_id, "转发抽奖", False)

    saved = _patch_pipeline(
        monkeypatch,
        classify=fake_classify,
        enrich=lambda client, **kwargs: _ok_activity(str(kwargs["dynamic_id"])),
    )

    result = run_new_links_pipeline(
        [f"https://www.bilibili.com/opus/{_BAD_ID}", f"https://www.bilibili.com/opus/{_OK_ID}"],
        workers=2,
    )

    assert result.ok is True
    assert result.skip_reasons[CLASSIFY_FAILED_REASON] == 1
    assert result.classified_count == 1
    assert result.enriched_count == 1
    assert result.persisted_count == 1
    assert len(saved) == 1
    assert saved[0]["dynamic_id"] == _OK_ID


def test_pipeline_continues_when_enrich_fails(monkeypatch) -> None:
    from src.pipeline.classify_step import ClassifyOutcome

    def fake_classify(client, dynamic_id):
        return ClassifyOutcome(dynamic_id, "转发抽奖", False)

    def fake_enrich(client, **kwargs):
        dynamic_id = str(kwargs["dynamic_id"])
        if dynamic_id == _BAD_ID:
            raise RuntimeError("HTTP 500 服务不可用")
        return _ok_activity(dynamic_id)

    saved = _patch_pipeline(monkeypatch, classify=fake_classify, enrich=fake_enrich)

    result = run_new_links_pipeline(
        [f"https://www.bilibili.com/opus/{_BAD_ID}", f"https://www.bilibili.com/opus/{_OK_ID}"],
        workers=2,
    )

    assert result.ok is True
    assert result.skip_reasons[ENRICH_FAILED_REASON] == 1
    assert result.enriched_count == 1
    assert result.persisted_count == 1
    assert len(saved) == 1
    assert saved[0]["dynamic_id"] == _OK_ID
