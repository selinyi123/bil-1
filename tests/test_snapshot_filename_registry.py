"""每个数据源都必须能读回自己的上一次快照。

`load_previous_output(path)` 拿**文件名**当键去查 DB 快照表，而那张 `FILENAME_TO_SOURCE`
是手写的，只登记了 ds1~ds7 与 watch。ds8/ds9/ds10 落在它外面，于是走文件回退——
而 `save_result` 只写 DB 不写文件，那些文件根本不存在，回退恒定返回 None。

后果不是丢数据（`updated=False` 时本就不保存），而是**报了假数**：
`web/actions.py` 无条件用 `len(result.activity_links)` 记日志与回执，
于是 DS-8/DS-9 在「无变化」路径上永远显示「共 0 条链接」，其余源显示真实条数。

修法不是往手写表里补两行——那是补症状，下一个数据源照样漏。
`SOURCE_OUTPUTS` 已经登记了全部 11 个源与文件名，让映射从它派生即可。
"""

from __future__ import annotations

from pathlib import Path

from src.db import init_db
from src.db.snapshots import save_ds_check_dict
from src.source_outputs import SOURCE_OUTPUTS
from src.sources.common import load_previous_output

LINKS = ["https://t.bilibili.com/1220298825599549447"]


def test_every_registered_source_reads_back_its_snapshot(isolated_home: Path) -> None:
    init_db()
    for source_id, path in SOURCE_OUTPUTS:
        if source_id == "WATCH":
            continue  # watch 走另一张快照表，由 watch_sync 的用例覆盖
        save_ds_check_dict(
            {
                "source_id": source_id,
                "updated": True,
                "activity_links": LINKS,
                "checked_at": 1,
            }
        )
        loaded = load_previous_output(path) or {}
        assert loaded.get("activity_links") == LINKS, f"{source_id} 读不回自己的快照"


def test_filename_registry_covers_every_source() -> None:
    """映射必须与数据源登记表一致——漏一个就是静默报 0 条。"""
    from src.db.snapshots import FILENAME_TO_SOURCE

    expected = {path.name: source_id for source_id, path in SOURCE_OUTPUTS}
    assert FILENAME_TO_SOURCE == expected
