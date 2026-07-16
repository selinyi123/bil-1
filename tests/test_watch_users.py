from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.source_outputs import SOURCE_OUTPUTS
from src.watch_feed import extract_feed_pub_ts, extract_forward_orig_id
from src.watch_sync import compute_sync_window
from src.watch_users import add_watch_user, list_watch_users, remove_watch_user, seed_from_candidates_if_empty
from web.actions import REFRESH_WATCH_TOTAL


def test_compute_sync_window_first_run() -> None:
    now = 1_000_000
    start, end = compute_sync_window(now=now, last_synced_at=None)
    assert end == now
    assert start == now - 10 * 24 * 3600


def test_compute_sync_window_incremental() -> None:
    now = 1_000_000
    last = now - 3600
    start, end = compute_sync_window(now=now, last_synced_at=last)
    assert start == last
    assert end == now


def test_compute_sync_window_caps_at_ten_days() -> None:
    now = 1_000_000
    last = now - 20 * 24 * 3600
    start, end = compute_sync_window(now=now, last_synced_at=last)
    assert start == now - 10 * 24 * 3600
    assert end == now


def test_extract_forward_orig_id_from_forward_item() -> None:
    item = {
        "type": "DYNAMIC_TYPE_FORWARD",
        "orig": {"id_str": "1208931614786060297"},
    }
    assert extract_forward_orig_id(item) == "1208931614786060297"


def test_extract_feed_pub_ts_from_module_dict() -> None:
    item = {
        "modules": {
            "module_author": {"pub_ts": "1784006862"},
        }
    }
    assert extract_feed_pub_ts(item) == 1784006862


def test_watch_users_crud(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    watch_path = tmp_path / "watch_users.json"
    candidates_path = tmp_path / "missing_candidates.json"
    monkeypatch.setattr("src.watch_users.WATCH_USERS_PATH", watch_path)
    monkeypatch.setattr("src.watch_users.CANDIDATES_PATH", candidates_path)
    monkeypatch.setattr(
        "src.watch_users.resolve_watch_user_name",
        lambda _client, mid: f"用户{mid}",
    )

    seed_from_candidates_if_empty()
    assert list_watch_users() == []

    add_watch_user(mid=123456)
    users = list_watch_users()
    assert len(users) == 1
    assert users[0].mid == 123456
    assert users[0].name == "用户123456"

    with pytest.raises(ValueError):
        add_watch_user(mid=123456)

    assert remove_watch_user(mid=123456) is True
    assert remove_watch_user(mid=123456) is False
    assert list_watch_users() == []


def test_seed_from_candidates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    watch_path = tmp_path / "watch_users.json"
    candidates_path = tmp_path / "candidates.json"
    candidates_path.write_text(
        json.dumps({"users": [{"mid": 42, "name": "候选"}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr("src.watch_users.WATCH_USERS_PATH", watch_path)
    monkeypatch.setattr("src.watch_users.CANDIDATES_PATH", candidates_path)

    assert seed_from_candidates_if_empty() is True
    users = list_watch_users()
    assert len(users) == 1
    assert users[0].mid == 42
    assert seed_from_candidates_if_empty() is False


def test_merge_registry_includes_watch() -> None:
    source_ids = [source_id for source_id, _ in SOURCE_OUTPUTS]
    assert "WATCH" in source_ids
    assert source_ids[-1] == "WATCH"


def test_refresh_watch_total_steps() -> None:
    assert REFRESH_WATCH_TOTAL == 4
