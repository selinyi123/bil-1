"""DS-8 手动 dyid 清单源（P1-2，源自 LAS 的 TxT 源）。

读取 `config/manual_dyids.txt`（每行一个动态 ID 或链接，支持逗号分隔），
把清单中的动态作为活动链接交给发现流水线。流水线负责去重与分类，
因此同一清单反复出现不会重复入库。

增量语义（P2 #11）：fingerprint = sha256(排序后的规范 ID 列表)，复用
`SourceCheckpointRow.cv_id` 列存储；清单未变 → updated=False（不触发流水线）。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from src.app_paths import config_dir
from src.sources.common import (
    CheckResult,
    fingerprint_of_text,
    load_previous_output,
    load_source_fingerprint,
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


def _fingerprint(ids: list[str]) -> str:
    """清单指纹：排序后的规范 ID 列表的 sha256（与顺序无关）。"""
    return fingerprint_of_text(json.dumps(sorted(ids), ensure_ascii=False))


def check_update(*, force: bool = False) -> CheckResult:
    ids = _read_manual_ids()
    links = [opus_link(did) for did in ids]
    previous = CONTAINER_PLACEHOLDER
    now = int(time.time())
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
            checked_at=now,
        )
    fp = _fingerprint(ids)
    if not force and load_source_fingerprint(SOURCE_ID) == fp:
        # 清单与上次成功处理的批次相同：无新内容
        prev_output = load_previous_output(OUTPUT_PATH)
        return CheckResult(
            source_id=SOURCE_ID,
            updated=False,
            container_url=previous,
            container_id="manual",
            title=f"手动清单（{len(links)} 条）",
            published_at=0,
            previous_container_url=previous,
            activity_links=(prev_output or {}).get("activity_links") or [],
            checked_at=now,
        )
    return CheckResult(
        source_id=SOURCE_ID,
        updated=True,
        container_url=previous,
        container_id="manual",
        title=f"手动清单（{len(links)} 条）",
        published_at=now,
        previous_container_url=previous,
        activity_links=links,
        checked_at=now,
        cv_id=fp,  # 复用 cv_id 承载 fingerprint，由 commit_source_checkpoint 持久化
    )


def save_result(result: CheckResult) -> Path | None:
    return write_result(OUTPUT_PATH, result)
