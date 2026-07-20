from __future__ import annotations

from pathlib import Path

from src.db.snapshots import load_ds_check_dict
from src.sources.common import (
    CheckResult,
    extract_t_bilibili_links_with_hints,
    save_result,
)


def test_extract_t_bilibili_links_with_hints() -> None:
    desc = (
        "互动抽奖\n"
        "https://t.bilibili.com/1234567890123456789\n"
        "转发抽奖\n"
        "https://t.bilibili.com/9876543210987654321"
    )
    links, hints = extract_t_bilibili_links_with_hints(desc)
    assert links == [
        "https://t.bilibili.com/1234567890123456789",
        "https://t.bilibili.com/9876543210987654321",
    ]
    assert hints == {
        "1234567890123456789": "互动抽奖",
        "9876543210987654321": "转发抽奖",
    }


def test_save_result_only_writes_on_update(isolated_home: Path) -> None:
    """写入隔离库；source_id 使用测试专用前缀，避免万一泄漏污染正式源列表。"""
    from src.db.engine import db_path

    assert db_path().resolve().is_relative_to(isolated_home.resolve())
    source_id = "__pytest_ds__"
    path = Path("ds_test.json")
    unchanged = CheckResult(
        source_id=source_id,
        updated=False,
        container_url="https://example.com/container",
        container_id="c1",
        title="title",
        published_at=1,
        previous_container_url="https://example.com/container",
        activity_links=["https://t.bilibili.com/1234567890123456789"],
        checked_at=99,
    )
    assert save_result(path, unchanged) is None
    assert load_ds_check_dict(source_id) is None

    updated = CheckResult(
        source_id=source_id,
        updated=True,
        container_url="https://example.com/container",
        container_id="c1",
        title="title",
        published_at=1,
        previous_container_url=None,
        activity_links=["https://t.bilibili.com/1234567890123456789"],
        checked_at=100,
    )
    saved = save_result(path, updated)
    assert saved == path
    data = load_ds_check_dict(source_id)
    assert data is not None
    assert data["updated"] is True
    assert data["checked_at"] == 100
