"""Line 多线路容灾 / 关注分区 / 清理（clear_follows）测试。"""
from __future__ import annotations

import time

from src.clear_follows import _item_dynamic_id, _item_pub_ts, clear_follows
from src.line import Line


# ---------------------------------------------------------------------------
# Line 多线路
# ---------------------------------------------------------------------------

def test_line_falls_back_to_next_on_failure() -> None:
    calls: list[int] = []

    def line_a():
        calls.append(0)
        raise RuntimeError("boom")

    def line_b():
        calls.append(1)
        return "ok"

    line = Line("test", [line_a, line_b], fallback=None)
    assert line.run() == "ok"
    assert calls == [0, 1]
    assert line.valid_line == 1  # 记住成功线路


def test_line_all_fail_returns_fallback() -> None:
    line = Line("test", [lambda: None, lambda: False], fallback="fallback")
    assert line.run() == "fallback"


def test_line_returns_first_valid() -> None:
    line = Line("test", [lambda: "first", lambda: "second"])
    assert line.run() == "first"


# ---------------------------------------------------------------------------
# 清理
# ---------------------------------------------------------------------------

def _space_item(dynamic_id: str, pub_ts: int, type_: int = 1) -> dict:
    """构造 space feed item；type_=1 为转发（可删），其他为原创（不删）。"""
    return {
        "id_str": dynamic_id,
        "modules": {
            "module_author": {"pub_ts": pub_ts},
            "module_dynamic": {"desc": {"type": type_}},
        },
    }


def test_item_extractors() -> None:
    assert _item_dynamic_id(_space_item("123", 1000)) == "123"
    assert _item_pub_ts(_space_item("123", 1000)) == 1000
    assert _item_pub_ts({"modules": [{"module_author": {"pub_ts": 2000}}]}) == 2000
    assert _item_pub_ts({"modules": {}}) == 0


def test_clear_follows_skips_original_dynamics(monkeypatch) -> None:
    """原创动态（desc.type != 1）即使超期也绝不删除。"""
    now = int(time.time())

    class FakeClient:
        def get_my_space_feed(self, offset=""):
            return {
                "items": [
                    _space_item("REPOST", now - 40 * 86400, type_=1),   # 转发 → 删
                    _space_item("ORIGIN", now - 40 * 86400, type_=2),   # 原创 → 跳过
                    _space_item("ORIGIN2", now - 40 * 86400, type_=0),  # 未知类型 → 跳过
                ],
                "has_more": False,
            }

        def delete_dynamic(self, dynamic_id):
            deleted.append(dynamic_id)
            return True

        def get_relation_tags(self):
            return []

    deleted: list[str] = []
    result = clear_follows(FakeClient(), max_days=30)
    assert result["deleted"] == 1
    assert deleted == ["REPOST"]
    assert result["skipped"] == 2


def test_clear_follows_max_days_floor(monkeypatch) -> None:
    """max_days<=0 时回落到 1 天，绝不触发全量删除。"""
    now = int(time.time())

    class FakeClient:
        def get_my_space_feed(self, offset=""):
            return {"items": [_space_item("OLD", now - 2 * 86400)], "has_more": False}

        def delete_dynamic(self, dynamic_id):
            return True

        def get_relation_tags(self):
            return []

    result = clear_follows(FakeClient(), max_days=0)
    # 2 天 > 1 天下限 → 仍删；重点是不抛错且不会因 0/负数放大范围
    assert result["deleted"] == 1
    result = clear_follows(FakeClient(), max_days=-5)
    assert result["deleted"] == 1
    # 非法字符串回落默认 30 天 → 2 天的动态不删
    result = clear_follows(FakeClient(), max_days="abc")
    assert result["deleted"] == 0


def test_clear_follows_deletes_expired_and_unfollows(monkeypatch) -> None:
    now = int(time.time())
    class FakeClient:
        def get_my_space_feed(self, offset=""):
            if offset == "":
                return {
                    "items": [
                        _space_item("OLD1", now - 31 * 86400),   # 超期 → 删
                        _space_item("NEW1", now - 1 * 86400),    # 未超期 → 留
                        _space_item("OLD2", now - 40 * 86400),   # 超期 → 删
                    ],
                    "has_more": False,
                }
            return None

        def delete_dynamic(self, dynamic_id):
            deleted.append(dynamic_id)
            return True

        def get_relation_tags(self):
            return [{"tagid": 7, "name": "抽奖临时关注"}]

        def get_partition_uids(self, tagid, pn=1, ps=50):
            if pn == 1:
                return [101, 102, 103]
            return []

        def cancel_attention(self, uid):
            unfollowed.append(uid)
            return True

    deleted: list[str] = []
    unfollowed: list[int] = []
    client = FakeClient()
    result = clear_follows(
        client,
        max_days=30,
        white_list="102",
        dry_run=False,
    )
    assert result["deleted"] == 2
    assert sorted(deleted) == ["OLD1", "OLD2"]
    assert result["unfollowed"] == 2
    assert sorted(unfollowed) == [101, 103]  # 102 在白名单
    assert result["scanned"] == 3


def test_clear_follows_dry_run_does_not_call_api(monkeypatch) -> None:
    now = int(time.time())

    class FakeClient:
        def get_my_space_feed(self, offset=""):
            return {"items": [_space_item("OLD", now - 31 * 86400)], "has_more": False}

        def delete_dynamic(self, dynamic_id):
            raise AssertionError("dry_run 不应调用 delete_dynamic")

        def get_relation_tags(self):
            return [{"tagid": 7, "name": "抽奖临时关注"}]

        def get_partition_uids(self, tagid, pn=1, ps=50):
            return [101]

        def cancel_attention(self, uid):
            raise AssertionError("dry_run 不应调用 cancel_attention")

    result = clear_follows(FakeClient(), max_days=30, dry_run=True)
    assert result["deleted"] == 1
    assert result["unfollowed"] == 1


# ---------------------------------------------------------------------------
# 关注分区
# ---------------------------------------------------------------------------

def test_ensure_participate_partition_finds_existing(monkeypatch) -> None:
    from src.lottery_actions import _ensure_participate_partition

    class FakeClient:
        def get_relation_tags(self):
            return [{"tagid": 3, "name": "其他"}, {"tagid": 9, "name": "抽奖临时关注"}]

        def create_relation_tag(self, name):
            raise AssertionError("已存在时不应创建")

    assert _ensure_participate_partition(FakeClient(), "抽奖临时关注") == 9


def test_ensure_participate_partition_creates_missing(monkeypatch) -> None:
    from src.lottery_actions import _ensure_participate_partition

    class FakeClient:
        def get_relation_tags(self):
            return []

        def create_relation_tag(self, name):
            return 42

    assert _ensure_participate_partition(FakeClient(), "抽奖临时关注") == 42
