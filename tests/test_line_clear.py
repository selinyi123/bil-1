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

def _space_item(
    dynamic_id: str,
    pub_ts: int,
    type_: int = 1,
    rid: str | None = None,
    author_mid: int | None = None,
) -> dict:
    """构造新版 polymer space feed item。

    - dynamic_id: 转发动态自身 id（id_str，删除接口用）
    - rid: 转发所指向的源动态 id（归属台账用）
    - author_mid: 源动态作者 mid（白名单保护用）
    """
    desc: dict = {"type": type_}
    if rid is not None:
        desc["rid"] = str(rid)
    origin: dict = {}
    if author_mid is not None:
        origin = {"modules": [{"module_author": {"mid": author_mid}}]}
    return {
        "id_str": dynamic_id,
        "modules": {
            "module_author": {"pub_ts": pub_ts},
            "module_dynamic": {"desc": desc, "origin": origin},
        },
    }


def _owned(*ids: str) -> frozenset[str]:
    """模拟 Binggo 归属台账（源动态 id 集合）。"""
    return frozenset(ids)


def test_item_extractors() -> None:
    assert _item_dynamic_id(_space_item("123", 1000)) == "123"
    assert _item_pub_ts(_space_item("123", 1000)) == 1000
    assert _item_pub_ts({"modules": [{"module_author": {"pub_ts": 2000}}]}) == 2000
    assert _item_pub_ts({"modules": {}}) == 0


def test_item_source_extractors() -> None:
    from src.clear_follows import _item_source_author_uid, _item_source_dynamic_id

    # 新版 polymer：desc.rid = 源动态 id；origin 内作者 mid
    item = _space_item("FWD1", 1000, rid="SRC1", author_mid=888)
    assert _item_source_dynamic_id(item) == "SRC1"
    assert _item_source_author_uid(item) == 888
    # 旧版 feed 结构：item.orig.id_str / item.orig.uid
    legacy = {"id_str": "FWD2", "orig": {"id_str": "SRC2", "uid": 999}}
    assert _item_source_dynamic_id(legacy) == "SRC2"
    assert _item_source_author_uid(legacy) == 999
    # 取不到源 id → 空串（触发归属跳过）
    assert _item_source_dynamic_id({"id_str": "X"}) == ""


def test_clear_follows_skips_original_dynamics(monkeypatch) -> None:
    """原创动态（desc.type != 1）即使超期也绝不删除。"""
    now = int(time.time())
    monkeypatch.setattr("src.clear_follows._owned_repost_dynamic_ids", lambda: _owned("REPOST"))

    class FakeClient:
        def get_my_space_feed(self, offset=""):
            return {
                "items": [
                    _space_item("FWD1", now - 40 * 86400, rid="REPOST"),        # Binggo 转发 → 删
                    _space_item("ORIGIN", now - 40 * 86400, type_=2),           # 原创 → 跳过
                    _space_item("ORIGIN2", now - 40 * 86400, type_=0),          # 未知类型 → 跳过
                ],
                "has_more": False,
            }

        def delete_dynamic(self, dynamic_id):
            deleted.append(dynamic_id)
            return True

        def get_relation_tags(self):
            return []

    deleted: list[str] = []
    result = clear_follows(FakeClient(), max_days=30, dry_run=False)
    assert result["deleted"] == 1
    # 删除的是转发动态自身 id，而非源 id
    assert deleted == ["FWD1"]
    assert result["skipped"] == 2


def test_clear_follows_ownership_uses_source_id_not_forward_id(monkeypatch) -> None:
    """归属校验必须用源动态 id（desc.rid）匹配台账：转发 id 在台账但源 id 不在 → 不删。"""
    now = int(time.time())
    monkeypatch.setattr("src.clear_follows._owned_repost_dynamic_ids", lambda: _owned("SRC-A"))

    class FakeClient:
        def get_my_space_feed(self, offset=""):
            return {
                "items": [
                    # 台账里有 SRC-A，但这条转发的源是 OTHER → 不删
                    _space_item("FWD-SRC-A", now - 400 * 86400, rid="OTHER"),
                    # 源 id 匹配台账 → 删（转发 id 不在台账也无妨）
                    _space_item("FWD-OTHER", now - 400 * 86400, rid="SRC-A"),
                ],
                "has_more": False,
            }

        def delete_dynamic(self, dynamic_id):
            deleted.append(dynamic_id)
            return True

        def get_relation_tags(self):
            return []

    deleted: list[str] = []
    result = clear_follows(FakeClient(), max_days=30, dry_run=False)
    assert deleted == ["FWD-OTHER"]
    assert result["deleted"] == 1
    assert result["skipped_unowned"] == 1


def test_clear_follows_never_deletes_unowned_reposts(monkeypatch) -> None:
    """核心不变量：非 Binggo 创建的转发（含用户手动转发）绝不删除。"""
    now = int(time.time())
    monkeypatch.setattr("src.clear_follows._owned_repost_dynamic_ids", lambda: _owned())

    class FakeClient:
        def get_my_space_feed(self, offset=""):
            return {"items": [_space_item("FWD-MANUAL", now - 400 * 86400, rid="MANUAL")], "has_more": False}

        def delete_dynamic(self, dynamic_id):
            raise AssertionError("非归属动态不应调用 delete_dynamic")

        def get_relation_tags(self):
            return []

    result = clear_follows(FakeClient(), max_days=30, dry_run=False)
    assert result["deleted"] == 0
    assert result["skipped_unowned"] == 1


def test_clear_follows_whitelist_protects_deletion(monkeypatch) -> None:
    """白名单作者的超期转发同样不删除（白名单同时保护删除与取关，按源作者匹配）。"""
    now = int(time.time())
    monkeypatch.setattr("src.clear_follows._owned_repost_dynamic_ids", lambda: _owned("WL"))

    class FakeClient:
        def get_my_space_feed(self, offset=""):
            return {
                "items": [_space_item("FWD-WL", now - 400 * 86400, rid="WL", author_mid=888)],
                "has_more": False,
            }

        def delete_dynamic(self, dynamic_id):
            raise AssertionError("白名单作者动态不应删除")

        def get_relation_tags(self):
            return []

    result = clear_follows(FakeClient(), max_days=30, white_list="888", dry_run=False)
    assert result["deleted"] == 0
    assert result["skipped_whitelist"] == 1


def test_clear_follows_max_days_floor(monkeypatch) -> None:
    """max_days<=0 时回落到 1 天，绝不触发全量删除。"""
    now = int(time.time())
    monkeypatch.setattr("src.clear_follows._owned_repost_dynamic_ids", lambda: _owned("OLD"))

    class FakeClient:
        def get_my_space_feed(self, offset=""):
            return {"items": [_space_item("FWD-OLD", now - 2 * 86400, rid="OLD")], "has_more": False}

        def delete_dynamic(self, dynamic_id):
            return True

        def get_relation_tags(self):
            return []

    result = clear_follows(FakeClient(), max_days=0, dry_run=False)
    # 2 天 > 1 天下限 → 仍删；重点是不抛错且不会因 0/负数放大范围
    assert result["deleted"] == 1
    result = clear_follows(FakeClient(), max_days=-5, dry_run=False)
    assert result["deleted"] == 1
    # 非法字符串回落默认 30 天 → 2 天的动态不删
    result = clear_follows(FakeClient(), max_days="abc", dry_run=False)
    assert result["deleted"] == 0


def test_clear_follows_deletes_expired_and_unfollows(monkeypatch) -> None:
    now = int(time.time())
    monkeypatch.setattr(
        "src.clear_follows._owned_repost_dynamic_ids", lambda: _owned("OLD1", "OLD2")
    )

    class FakeClient:
        def get_my_space_feed(self, offset=""):
            if offset == "":
                return {
                    "items": [
                        _space_item("FWD-OLD1", now - 31 * 86400, rid="OLD1"),  # 超期 → 删
                        _space_item("FWD-NEW1", now - 1 * 86400, rid="NEW1"),   # 未超期 → 留
                        _space_item("FWD-OLD2", now - 40 * 86400, rid="OLD2"),  # 超期 → 删
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
    assert sorted(deleted) == ["FWD-OLD1", "FWD-OLD2"]
    assert result["unfollowed"] == 2
    assert sorted(unfollowed) == [101, 103]  # 102 在白名单
    assert result["scanned"] == 3


def test_clear_follows_dry_run_does_not_call_api(monkeypatch) -> None:
    now = int(time.time())
    monkeypatch.setattr("src.clear_follows._owned_repost_dynamic_ids", lambda: _owned("OLD"))

    class FakeClient:
        def get_my_space_feed(self, offset=""):
            return {"items": [_space_item("FWD-OLD", now - 31 * 86400, rid="OLD")], "has_more": False}

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
