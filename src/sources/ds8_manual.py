"""DS-8 手动 dyid 清单源（P1-2，源自 LAS 的 TxT 源）。

读取 `config/manual_dyids.txt`（每行一个动态 ID 或链接，支持逗号分隔），
把清单中的动态作为活动链接交给发现流水线。流水线负责去重与分类，
因此同一清单反复出现不会重复入库。
"""
from __future__ import annotations

import time
from pathlib import Path

from src.app_paths import config_dir
from src.sources.common import (
    CheckResult,
    load_previous_output,
    normalize_dynamic_id,
    opus_link,
    save_result as write_result,
)
from src.state_store import DATA_DIR

SOURCE_ID = "DS-8"
OUTPUT_PATH = DATA_DIR / "output" / "ds8_latest.json"
CONFIG_FILE = config_dir() / "manual_dyids.txt"
CONTAINER_PLACEHOLDER = "manual://list"


def _read_manual_ids() -> list[str]:
    """读取手动清单文件，返回去重后的规范动态 ID 列表；文件缺失/空返回 []。"""
    path = CONFIG_FILE
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    ids: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        for token in line.replace(",", "\n").splitlines():
            token = token.strip()
            if not token:
                continue
            dynamic_id = normalize_dynamic_id(token)
            if not dynamic_id or dynamic_id in seen:
                continue
            seen.add(dynamic_id)
            ids.append(dynamic_id)
    return ids


def check_update(*, force: bool = False) -> CheckResult:
    ids = _read_manual_ids()
    links = [opus_link(did) for did in ids]
    previous = CONTAINER_PLACEHOLDER
    if not links:
        prev_output = load_previous_output(OUTPUT_PATH)
        return CheckResult(
            source_id=SOURCE_ID,
            updated=False,
            container_url=previous,
            container_id="",
            title="手动清单（空）",
            published_at=0,
            previous_container_url=previous,
            activity_links=(prev_output or {}).get("activity_links") or [],
            checked_at=int(time.time()),
        )
    return CheckResult(
        source_id=SOURCE_ID,
        updated=True,
        container_url=previous,
        container_id="manual",
        title=f"手动清单（{len(links)} 条）",
        published_at=int(time.time()),
        previous_container_url=previous,
        activity_links=links,
        checked_at=int(time.time()),
    )


def save_result(result: CheckResult) -> Path | None:
    return write_result(OUTPUT_PATH, result)
