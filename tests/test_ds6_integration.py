from __future__ import annotations

from web.actions import DS_HANDLERS, REFRESH_ALL_TOTAL, REFRESH_WATCH_TOTAL
from web.activity_service import DS_OUTPUTS, SOURCE_LABELS, SOURCE_SPACE_URLS
from src.source_outputs import SOURCE_OUTPUTS


def test_all_registries_include_latest_ds_and_watch() -> None:
    handler_ids = [source_id for source_id, _, _ in DS_HANDLERS]
    merge_ids = [source_id for source_id, _ in SOURCE_OUTPUTS]
    output_ids = sorted(DS_OUTPUTS.keys())

    assert handler_ids == merge_ids[: len(handler_ids)]
    assert "DS-7" in handler_ids
    assert "WATCH" in merge_ids
    assert "WATCH" in output_ids
    assert len(handler_ids) == 7
    assert len(merge_ids) == 8


def test_refresh_all_total_matches_handlers() -> None:
    assert REFRESH_ALL_TOTAL == len(DS_HANDLERS) + 3


def test_ds7_metadata() -> None:
    assert SOURCE_LABELS["DS-7"] == "大锦鲤"
    assert SOURCE_SPACE_URLS["DS-7"] == "https://space.bilibili.com/226257459/upload/opus"
    assert DS_OUTPUTS["DS-7"].name == "ds7_latest.json"
    assert SOURCE_LABELS["WATCH"] == "监控用户"
    assert DS_OUTPUTS["WATCH"].name == "watch_latest.json"


def test_ds6_metadata_unchanged() -> None:
    assert SOURCE_LABELS["DS-6"] == "糯米是个背包"
    assert SOURCE_SPACE_URLS["DS-6"] == "https://space.bilibili.com/492426375/upload/opus"
    assert DS_OUTPUTS["DS-6"].name == "ds6_latest.json"
