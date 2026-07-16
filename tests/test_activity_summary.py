from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from web.activity_service import get_summary


def test_get_summary_counts_are_consistent(tmp_path, monkeypatch) -> None:
    path = tmp_path / "activities_latest.json"
    payload = {
        "updated_at": 1,
        "activities": [
            {
                "dynamic_id": "1",
                "lottery_type": "转发抽奖",
                "draw_status": "active",
                "activity_status": "未参加",
            },
            {
                "dynamic_id": "2",
                "lottery_type": "互动抽奖",
                "draw_status": "ended",
                "activity_status": "已结束",
            },
            {
                "dynamic_id": "3",
                "lottery_type": "充电抽奖",
                "skipped": True,
                "draw_status": "active",
                "activity_status": "未参加",
            },
            {
                "dynamic_id": "4",
                "lottery_type": "转发抽奖",
                "skipped": True,
                "skip_reason": "非抽奖活动",
                "draw_status": "active",
            },
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr("web.activity_service.load_participations", lambda: {})
    monkeypatch.setattr("web.activity_service.load_payload", lambda: payload)

    summary = get_summary()
    status = summary["user_status_counts"]
    draw = summary["counts"]

    assert summary["total_count"] == 2
    assert status["未参加"] + status["已参加"] + status["已结束"] == 2
    assert draw["active"] + draw["ended"] == 2
    assert draw == {"active": 1, "ended": 1}


def test_get_summary_loads_seeded_activities(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seed_activities = [
        {
            "dynamic_id": "1001",
            "lottery_type": "互动抽奖",
            "draw_status": "active",
            "activity_status": "未参加",
            "lottery_time": int(time.time()) + 3600,
            "prizes": [{"description": "测试奖品", "winner_count": 1}],
            "repost_count": 10,
            "repost_fetched": True,
        }
    ]
    seed_path = tmp_path / "config" / "activities_seed.json"
    seed_path.parent.mkdir(parents=True)
    seed_path.write_text(
        json.dumps({"seed_version": 1, "activities": seed_activities}, ensure_ascii=False),
        encoding="utf-8",
    )

    data_dir = tmp_path / "data"
    monkeypatch.setattr("src.state_store.DATA_DIR", data_dir)
    monkeypatch.setattr("src.activity_store.DATA_DIR", data_dir)
    monkeypatch.setattr("src.activity_store.ACTIVITIES_OUTPUT_PATH", data_dir / "output" / "activities_latest.json")
    monkeypatch.setattr("web.activity_service.DATA_DIR", data_dir)
    monkeypatch.setattr("src.activity_seed.CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr("src.activity_seed.USER_SEED_PATH", seed_path)
    monkeypatch.setattr("src.activity_seed.BUNDLED_SEED_PATH", seed_path)
    monkeypatch.setattr("src.app_paths.user_home", lambda: tmp_path)
    monkeypatch.setattr("web.activity_service.load_participations", lambda: {})

    from src.app_paths import ensure_user_dirs

    ensure_user_dirs()
    summary = get_summary()
    assert summary["total_count"] == 1
    assert summary["counts"]["active"] == 1
