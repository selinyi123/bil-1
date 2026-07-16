from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.state_store import get_last_pipeline_persisted, set_last_pipeline_persisted
from web.activity_service import get_summary


def test_last_pipeline_persisted_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_path = tmp_path / "state.json"
    monkeypatch.setattr("src.state_store.STATE_PATH", state_path)

    assert get_last_pipeline_persisted() == {
        "action": "",
        "persisted_count": 0,
        "synced_at": None,
    }

    set_last_pipeline_persisted(action="refresh_watch", persisted_count=5, synced_at=1_700_000_000)
    assert get_last_pipeline_persisted() == {
        "action": "refresh_watch",
        "persisted_count": 5,
        "synced_at": 1_700_000_000,
    }

    set_last_pipeline_persisted(action="refresh_all", persisted_count=12)
    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved["pipeline"]["last_action"] == "refresh_all"
    assert saved["pipeline"]["last_persisted_count"] == 12
    assert get_last_pipeline_persisted()["persisted_count"] == 12


def test_get_summary_uses_last_pipeline_persisted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    activities_path = tmp_path / "activities_latest.json"
    activities_path.write_text(
        json.dumps(
            {
                "updated_at": 1,
                "activities": [
                    {
                        "dynamic_id": "1",
                        "lottery_type": "转发抽奖",
                        "draw_status": "active",
                        "activity_status": "未参加",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "pipeline": {
                    "last_action": "refresh_all",
                    "last_persisted_count": 7,
                    "last_synced_at": 1_700_000_001,
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("web.activity_service.ACTIVITIES_OUTPUT_PATH", activities_path)
    monkeypatch.setattr("src.state_store.STATE_PATH", state_path)
    monkeypatch.setattr("web.activity_service.load_participations", lambda: {})
    monkeypatch.setattr(
        "web.activity_service._load_json",
        lambda p: json.loads(activities_path.read_text(encoding="utf-8")),
    )

    summary = get_summary()
    assert summary["new_count"] == 7
    assert summary["last_pipeline_sync"]["action"] == "refresh_all"
