from __future__ import annotations

from pathlib import Path

import pytest

from src.activity_store import replace_all_activities
from src.state_store import get_last_pipeline_persisted, set_last_pipeline_persisted
from web.activity_service import get_summary


def test_last_pipeline_persisted_roundtrip(isolated_home: Path) -> None:
    _ = isolated_home
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
    assert get_last_pipeline_persisted()["action"] == "refresh_all"
    assert get_last_pipeline_persisted()["persisted_count"] == 12


def test_get_summary_uses_last_pipeline_persisted(
    isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    replace_all_activities(
        [
            {
                "dynamic_id": "1",
                "lottery_type": "转发抽奖",
                "draw_status": "active",
                "activity_status": "未参加",
            }
        ]
    )
    set_last_pipeline_persisted(
        action="refresh_all",
        persisted_count=7,
        synced_at=1_700_000_001,
    )
    monkeypatch.setattr("web.activity_service.load_participations", lambda: {})

    summary = get_summary()
    assert summary["new_count"] == 7
    assert summary["last_pipeline_sync"]["action"] == "refresh_all"
