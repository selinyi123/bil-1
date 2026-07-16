from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from src.activity_seed import (
    extract_seed_activities,
    is_activity_seedable,
    read_seed_activities,
    sanitize_seed_activity,
)
from src.activity_store import ACTIVITIES_OUTPUT_PATH, load_activities, seed_activities_if_empty


def test_sanitize_seed_activity_clears_user_state() -> None:
    item = {
        "dynamic_id": "123",
        "activity_status": "已参加",
        "platform_participated": True,
        "draw_status": "active",
        "draw_tag": "即将开奖",
        "lottery_type": "互动抽奖",
    }
    clean = sanitize_seed_activity(item)
    assert clean["activity_status"] == "未参加"
    assert "platform_participated" not in clean
    assert clean["draw_tag"] == ""


def test_is_activity_seedable_skips_ended() -> None:
    now = int(time.time())
    active = {"dynamic_id": "1", "draw_status": "active", "lottery_time": now + 3600}
    ended = {"dynamic_id": "2", "draw_status": "ended"}
    assert is_activity_seedable(active, now=now) is True
    assert is_activity_seedable(ended, now=now) is False


def test_extract_seed_activities_filters_and_sanitizes() -> None:
    now = int(time.time())
    payload = {
        "activities": [
            {
                "dynamic_id": "1",
                "draw_status": "active",
                "activity_status": "已参加",
                "platform_participated": True,
                "lottery_time": now + 3600,
            },
            {"dynamic_id": "2", "draw_status": "ended"},
        ]
    }
    rows = extract_seed_activities(payload, now=now)
    assert len(rows) == 1
    assert rows[0]["dynamic_id"] == "1"
    assert rows[0]["activity_status"] == "未参加"


def test_seed_activities_if_empty_writes_payload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seed = {
        "seed_version": 1,
        "activities": [
            {
                "dynamic_id": "999",
                "lottery_type": "互动抽奖",
                "draw_status": "active",
                "activity_status": "已参加",
                "platform_participated": True,
                "lottery_time": int(time.time()) + 7200,
            }
        ],
    }
    seed_path = tmp_path / "config" / "activities_seed.json"
    seed_path.parent.mkdir(parents=True)
    seed_path.write_text(json.dumps(seed, ensure_ascii=False), encoding="utf-8")

    data_dir = tmp_path / "data"
    monkeypatch.setattr("src.state_store.DATA_DIR", data_dir)
    monkeypatch.setattr("src.activity_store.DATA_DIR", data_dir)
    monkeypatch.setattr("src.activity_store.ACTIVITIES_OUTPUT_PATH", data_dir / "output" / "activities_latest.json")
    monkeypatch.setattr("src.activity_seed.CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr("src.activity_seed.USER_SEED_PATH", seed_path)
    monkeypatch.setattr("src.activity_seed.BUNDLED_SEED_PATH", seed_path)

    assert seed_activities_if_empty() is True
    assert ACTIVITIES_OUTPUT_PATH.exists()
    activities = load_activities()
    assert len(activities) == 1
    assert activities[0]["dynamic_id"] == "999"
    assert activities[0]["activity_status"] == "未参加"
    assert seed_activities_if_empty() is False


def test_bundled_seed_file_exists() -> None:
  root = Path(__file__).resolve().parents[1]
  seed_path = root / "config" / "activities_seed.json"
  assert seed_path.is_file()
  payload = json.loads(seed_path.read_text(encoding="utf-8"))
  assert payload.get("activity_count", 0) > 0
  assert len(payload.get("activities") or []) > 0
