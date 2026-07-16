from __future__ import annotations

from src.pipeline.refresh_all_pipeline import run_new_links_pipeline


def test_enrich_progress_updates_every_item(monkeypatch) -> None:
    events: list[tuple[int, int, str]] = []

    def fake_classify(client, dynamic_id):
        from src.pipeline.classify_step import ClassifyOutcome

        return ClassifyOutcome(dynamic_id, "互动抽奖", False)

    notice = {
        "lottery_id": 1,
        "first_prize": 1,
        "first_prize_cmt": "奖",
        "lottery_time": 9999999999,
    }
    raw_item = {
        "modules": {
            "module_stat": {"forward": {"count": 1}},
            "module_dynamic": {"major": {"type": "MAJOR_TYPE_DRAW"}},
        }
    }

    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.known_activity_ids", lambda: set())
    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.classify_new_link", fake_classify)
    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.load_participations", lambda: {})
    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.append_activities", lambda rows: len(rows))
    monkeypatch.setattr("src.pipeline.enrich_fetch_context.fetch_dynamic_detail", lambda *args, **kwargs: raw_item)
    monkeypatch.setattr(
        "src.lottery_enricher.fetch_notice_for_interact",
        lambda client, dynamic_id: (notice, 1, dynamic_id),
    )
    monkeypatch.setattr("src.lottery_enricher.is_upower_dynamic", lambda item: False)

    run_new_links_pipeline(
        [
            "https://www.bilibili.com/opus/1220760006294503425",
            "https://www.bilibili.com/opus/1220760006294503426",
        ],
        workers=2,
        on_progress=lambda done, total, msg: events.append((done, total, msg)),
    )

    detail_events = [event for event in events if event[2] == "详情进度"]
    assert detail_events == [(1, 2, "详情进度"), (2, 2, "详情进度")]
