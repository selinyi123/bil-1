from __future__ import annotations

import pytest

from src.clear_follows import DEFAULT_PARTITION_NAME, _resolve_partition_name


def test_cleanup_uses_enabled_enhance_partition(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.participate_enhance.load_participate_enhance",
        lambda: {"partition": {"enabled": True, "name": "我的抽奖关注"}},
    )
    # 未显式指定 → 沿用配置中启用的分区
    assert _resolve_partition_name(None) == "我的抽奖关注"
    assert _resolve_partition_name("") == "我的抽奖关注"


def test_cleanup_keeps_default_when_partition_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.participate_enhance.load_participate_enhance",
        lambda: {"partition": {"enabled": False, "name": "我的抽奖关注"}},
    )
    assert _resolve_partition_name(None) == DEFAULT_PARTITION_NAME


def test_cleanup_explicit_default_partition_not_redirected(monkeypatch: pytest.MonkeyPatch) -> None:
    """显式传默认分区名时不被配置重定向（修复：显式请求默认分区被静默改道）。"""
    monkeypatch.setattr(
        "src.participate_enhance.load_participate_enhance",
        lambda: {"partition": {"enabled": True, "name": "我的抽奖关注"}},
    )
    assert _resolve_partition_name(DEFAULT_PARTITION_NAME) == DEFAULT_PARTITION_NAME


def test_cleanup_explicit_partition_override_has_priority(monkeypatch: pytest.MonkeyPatch) -> None:
    def _must_not_load() -> dict:
        raise AssertionError("explicit partition must not consult enhance config")

    monkeypatch.setattr("src.participate_enhance.load_participate_enhance", _must_not_load)
    assert _resolve_partition_name("手工清理分区") == "手工清理分区"


class _ShrinkingPartitionClient:
    """模拟真实分区接口：取关会让分区集合收缩，后续分页随之偏移。

    这正是"边翻页边删除"会漏取关的机制——第 1 页删空后，原第 2 页成员
    补位成新的第 1 页，而循环已经在请求 pn=2。
    """

    PAGE = 50

    def __init__(self, members: list[int]) -> None:
        self.members = list(members)
        self.page_requests: list[int] = []

    # 第一阶段（删除自己的转发）在本用例中不参与
    def get_my_space_feed(self, offset: str = "") -> dict:
        return {"items": [], "has_more": False, "offset": ""}

    def get_relation_tags(self) -> list[dict]:
        return [{"name": DEFAULT_PARTITION_NAME, "tagid": 42}]

    def get_partition_uids(self, tagid: int, pn: int = 1) -> list[int]:
        self.page_requests.append(pn)
        start = (pn - 1) * self.PAGE
        return self.members[start : start + self.PAGE]

    def cancel_attention(self, uid: int) -> bool:
        if uid in self.members:
            self.members.remove(uid)
            return True
        return False


def test_partition_members_are_read_fully_before_unfollowing() -> None:
    """>50 人分区必须全部取关，不能因分页集合收缩而跳过整批成员。"""
    from src.clear_follows import clear_follows

    members = list(range(1000, 1120))  # 120 人，跨 3 页
    client = _ShrinkingPartitionClient(members)

    result = clear_follows(
        client,  # type: ignore[arg-type]
        delete_dynamic=False,
        partition_name=DEFAULT_PARTITION_NAME,
        dry_run=False,
    )

    assert result["unfollowed"] == 120, f"漏取关 {120 - result['unfollowed']} 人"
    assert client.members == [], "分区仍有残留成员"
    # 全部读完再删：分页请求发生在任何取关之前，页码连续
    assert client.page_requests == [1, 2, 3]


def test_partition_whitelist_survives_full_read() -> None:
    from src.clear_follows import clear_follows

    client = _ShrinkingPartitionClient(list(range(1000, 1060)))  # 60 人，跨 2 页
    result = clear_follows(
        client,  # type: ignore[arg-type]
        delete_dynamic=False,
        white_list="1000,1059",
        partition_name=DEFAULT_PARTITION_NAME,
        dry_run=False,
    )
    assert result["unfollowed"] == 58
    assert sorted(client.members) == [1000, 1059]


def test_partition_dry_run_matches_real_run_count() -> None:
    """预演与真实执行必须给出同一个数字。

    旧实现里 dry_run 不删除、集合不收缩，因此预演能扫全量而真实执行会跳页——
    预演反而给出与实际不符的预期，比单纯漏删更容易误导。
    """
    from src.clear_follows import clear_follows

    members = list(range(2000, 2135))  # 135 人，跨 3 页

    preview = clear_follows(
        _ShrinkingPartitionClient(members),  # type: ignore[arg-type]
        delete_dynamic=False,
        partition_name=DEFAULT_PARTITION_NAME,
        dry_run=True,
    )
    real = clear_follows(
        _ShrinkingPartitionClient(members),  # type: ignore[arg-type]
        delete_dynamic=False,
        partition_name=DEFAULT_PARTITION_NAME,
        dry_run=False,
    )
    assert preview["unfollowed"] == real["unfollowed"] == 135
