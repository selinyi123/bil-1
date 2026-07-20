from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.state_seed import read_seed_state, sanitize_seed_state
from src.state_store import get_last_container, load_state, seed_state_if_missing


def test_sanitize_seed_state_keeps_sources_and_watch() -> None:
    payload = {
        "sources": {
            "DS-1": {
                "container_url": "https://example.com/video/BV1",
                "container_id": "BV1",
                "title": "demo",
                "checked_at": 100,
            },
            "DS-9": {"container_url": "https://example.com/ignored"},
        },
        "watch": {"last_synced_at": 200},
        "pipeline": {"last_action": "refresh_all", "last_persisted_count": 99},
    }
    cleaned = sanitize_seed_state(payload)
    assert list(cleaned["sources"]) == ["DS-1"]
    assert cleaned["watch"]["last_synced_at"] == 200
    assert "pipeline" not in cleaned


def test_seed_state_if_missing_writes_payload(
    isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed = {
        "seed_version": 1,
        "sources": {
            "DS-2": {
                "container_url": "https://example.com/read/cv1",
                "container_id": "cv1",
                "checked_at": 123,
            }
        },
        "watch": {"last_synced_at": 456},
    }
    seed_path = isolated_home / "config" / "state_seed.json"
    seed_path.parent.mkdir(parents=True, exist_ok=True)
    seed_path.write_text(json.dumps(seed, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr("src.state_seed.CONFIG_DIR", isolated_home / "config")
    monkeypatch.setattr("src.state_seed.USER_STATE_SEED_PATH", seed_path)
    monkeypatch.setattr("src.state_seed.BUNDLED_STATE_SEED_PATH", seed_path)

    assert seed_state_if_missing() is True
    loaded = load_state()
    assert loaded["sources"]["DS-2"]["container_url"].endswith("/cv1")
    assert loaded["watch"]["last_synced_at"] == 456
    assert get_last_container("DS-2") == "https://example.com/read/cv1"
    assert seed_state_if_missing() is False


def test_bundled_state_seed_has_all_sources() -> None:
    root = Path(__file__).resolve().parents[1]
    seed_path = root / "config" / "state_seed.json"
    assert seed_path.is_file()
    payload = json.loads(seed_path.read_text(encoding="utf-8"))
    sources = payload.get("sources") or {}
    assert len(sources) == 6
    assert read_seed_state()["sources"]
