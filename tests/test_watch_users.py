from __future__ import annotations

import json
import time
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


def test_watch_users_crud(isolated_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    watch_path = isolated_home / "config" / "watch_users.json"
    candidates_path = isolated_home / "config" / "missing_candidates.json"
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

    assert remove_watch_user(mid=123456) is True
    assert remove_watch_user(mid=123456) is False
    assert list_watch_users() == []


def test_seed_from_candidates(isolated_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    watch_path = isolated_home / "config" / "watch_users.json"
    candidates_path = isolated_home / "config" / "candidates.json"
    candidates_path.parent.mkdir(parents=True, exist_ok=True)
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


# ---------- #8：sync_watch_forwards 部分失败判定 ----------


class _FakeBiliClient:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


def test_sync_watch_forwards_partial_failure_not_raised(
    isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """9 用户成功但无转发 + 1 用户失败 → 不整体抛错，users_ok 正确统计。"""
    from src.watch_sync import sync_watch_forwards
    from src.watch_users import WatchUser

    users = [WatchUser(mid=i, name=f"u{i}") for i in range(1, 11)]

    def fake_collect(client, mid, *, since_ts, until_ts, stats=None):
        if mid == 10:
            raise RuntimeError("模拟用户扫描失败")
        return []

    monkeypatch.setattr("src.watch_sync.BilibiliClient", _FakeBiliClient)
    monkeypatch.setattr("src.watch_sync.collect_forward_links_for_user", fake_collect)
    monkeypatch.setattr("src.watch_sync.get_watch_last_synced_at", lambda: None)

    result = sync_watch_forwards(users=users)
    assert result.users_ok == 9
    assert len(result.users_failed) == 1
    assert result.users_failed[0]["mid"] == 10
    assert result.activity_links == []
    assert result.link_count == 0


def test_sync_watch_forwards_all_failed_raises(
    isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.watch_sync import sync_watch_forwards
    from src.watch_users import WatchUser

    def fake_collect(client, mid, *, since_ts, until_ts, stats=None):
        raise RuntimeError("全部失败")

    monkeypatch.setattr("src.watch_sync.BilibiliClient", _FakeBiliClient)
    monkeypatch.setattr("src.watch_sync.collect_forward_links_for_user", fake_collect)
    monkeypatch.setattr("src.watch_sync.get_watch_last_synced_at", lambda: None)

    with pytest.raises(RuntimeError, match="全部"):
        sync_watch_forwards(users=[WatchUser(mid=1, name="a"), WatchUser(mid=2, name="b")])


# ---------- #33：无 pub_ts 的转发条目必须跳过 ----------


def test_collect_forward_links_skips_items_without_pub_ts() -> None:
    """pub_ts 缺失的 item 不收集、不伪造时间戳（不视为窗口内/当前时间）。"""
    from src.watch_feed import collect_forward_links_for_user

    now = int(time.time())
    VALID_A = "1208931614786060297"
    VALID_B = "1208931614786060298"

    class _FeedClient:
        def get_json(self, url, **kwargs):
            return {
                "code": 0,
                "data": {
                    "items": [
                        # 无 pub_ts → 跳过（此前会被视为当前时间收集）
                        {
                            "type": "DYNAMIC_TYPE_FORWARD",
                            "orig": {"id_str": VALID_A},
                            "id_str": "feed-id-a",
                            "modules": {},
                        },
                        # 窗口内 → 收集
                        {
                            "type": "DYNAMIC_TYPE_FORWARD",
                            "orig": {"id_str": VALID_B},
                            "id_str": "feed-id-b",
                            "modules": {"module_author": {"pub_ts": now}},
                        },
                    ],
                    "offset": "",
                },
            }

    stats: dict = {}
    links = collect_forward_links_for_user(
        _FeedClient(),
        123456,
        since_ts=now - 3600,
        until_ts=now,
        stats=stats,
    )
    assert [link.dynamic_id for link in links] == [VALID_B]
    assert stats.get("skipped_no_pub_ts") == 1


def test_collect_forward_links_no_pub_ts_all_skipped() -> None:
    """全部条目无 pub_ts → 收集结果为空且不伪造时间戳。"""
    from src.watch_feed import collect_forward_links_for_user

    now = int(time.time())

    class _EmptyFeedClient:
        def get_json(self, url, **kwargs):
            return {
                "code": 0,
                "data": {
                    "items": [
                        {
                            "type": "DYNAMIC_TYPE_FORWARD",
                            "orig": {"id_str": "1208931614786060297"},
                            "id_str": "feed-id-a",
                            "modules": {},
                        }
                    ],
                    "offset": "",
                },
            }

    stats: dict = {}
    links = collect_forward_links_for_user(
        _EmptyFeedClient(), 123456, since_ts=now - 3600, until_ts=now, stats=stats
    )
    assert links == []
    assert stats.get("skipped_no_pub_ts") == 1
