from __future__ import annotations

import pytest

from src.clear_follows import DEFAULT_PARTITION_NAME, _resolve_partition_name


def test_cleanup_uses_enabled_enhance_partition(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.participate_enhance.load_participate_enhance",
        lambda: {"partition": {"enabled": True, "name": "我的抽奖关注"}},
    )
    assert _resolve_partition_name(DEFAULT_PARTITION_NAME) == "我的抽奖关注"


def test_cleanup_keeps_default_when_partition_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.participate_enhance.load_participate_enhance",
        lambda: {"partition": {"enabled": False, "name": "我的抽奖关注"}},
    )
    assert _resolve_partition_name(DEFAULT_PARTITION_NAME) == DEFAULT_PARTITION_NAME


def test_cleanup_explicit_partition_override_has_priority(monkeypatch: pytest.MonkeyPatch) -> None:
    def _must_not_load() -> dict:
        raise AssertionError("explicit partition must not consult enhance config")

    monkeypatch.setattr("src.participate_enhance.load_participate_enhance", _must_not_load)
    assert _resolve_partition_name("手工清理分区") == "手工清理分区"
