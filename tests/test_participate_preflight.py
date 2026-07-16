from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.participate_preflight import ensure_activity_participatable


def _write_enriched(path: Path, item: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"activities": [item], "total_count": 1}, ensure_ascii=False),
        encoding="utf-8",
    )


def test_ensure_activity_participatable_rejects_joined(tmp_path: Path, monkeypatch) -> None:
    enriched = tmp_path / "enriched_latest.json"
    dynamic_id = "1000000000000000001"
    _write_enriched(
        enriched,
        {
            "dynamic_id": dynamic_id,
            "lottery_type": "互动抽奖",
            "activity_status": "未参加",
            "draw_status": "active",
            "lottery_time": 9_999_999_999,
            "conditions": {},
        },
    )

    monkeypatch.setattr("src.participate_preflight.ENRICHED_OUTPUT_PATH", enriched)
    monkeypatch.setattr("src.status_refresh.ENRICHED_OUTPUT_PATH", enriched)

    notice = {
        "participated": True,
        "lottery_time": 9_999_999_999,
        "status": 0,
    }
    client = MagicMock()
    monkeypatch.setattr(
        "src.participate_preflight.fetch_dynamic_detail",
        lambda _client, _did: {"modules": {}},
    )
    monkeypatch.setattr("src.participate_preflight.is_upower_dynamic", lambda _item: False)
    monkeypatch.setattr(
        "src.participate_preflight.fetch_notice_for_interact",
        lambda _client, _did: (notice, 0, dynamic_id),
    )
    monkeypatch.setattr("src.participate_preflight.load_participations", lambda: {})

    with pytest.raises(RuntimeError, match="已参加"):
        ensure_activity_participatable(client, dynamic_id, lottery_type_hint="互动抽奖")
