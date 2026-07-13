from __future__ import annotations

from web.actions import DS_HANDLERS, REFRESH_ALL_TOTAL
from web.activity_service import DS_OUTPUTS, SOURCE_LABELS, SOURCE_SPACE_URLS
from src.merge_links import SOURCE_OUTPUTS


def test_all_registries_include_ds6() -> None:
    handler_ids = [source_id for source_id, _, _ in DS_HANDLERS]
    merge_ids = [source_id for source_id, _ in SOURCE_OUTPUTS]
    output_ids = sorted(DS_OUTPUTS.keys())

    assert handler_ids == merge_ids == output_ids
    assert "DS-6" in handler_ids
    assert len(handler_ids) == 6


def test_refresh_all_total_matches_handlers() -> None:
    assert REFRESH_ALL_TOTAL == len(DS_HANDLERS) + 4


def test_ds6_metadata() -> None:
    assert SOURCE_LABELS["DS-6"] == "糯米是个背包"
    assert SOURCE_SPACE_URLS["DS-6"] == "https://space.bilibili.com/492426375/upload/opus"
    assert DS_OUTPUTS["DS-6"].name == "ds6_latest.json"
