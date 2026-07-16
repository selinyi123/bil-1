from __future__ import annotations

import json
from pathlib import Path

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


def test_save_result_only_writes_on_update(tmp_path: Path) -> None:
    path = tmp_path / "ds_test.json"
    unchanged = CheckResult(
        source_id="DS-TEST",
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
    assert not path.exists()

    updated = CheckResult(
        source_id="DS-TEST",
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
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["updated"] is True
    assert data["checked_at"] == 100
