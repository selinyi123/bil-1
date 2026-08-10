"""DS-9 话题源（P1-3，源自 LAS 的 TAGs 源）。

读取 `config/topic_tags.txt`（每行一个话题名），
逐个话题拉取热门（topic/new）+ 历史（topic/history）动态，
把话题内动态 ID 作为活动链接交给发现流水线。

增量语义（P2 #11）：每轮只抓 topic/new（最新一页）计算 fingerprint
（= 话题名 + 每话题最新动态 id 集合的 sha256，复用 `SourceCheckpointRow.cv_id`
列存储）；fingerprint 未变 → updated=False 且不抓多页历史（省网络）；
仅当 fingerprint 变化或 force 时才抓多页历史并入库。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from src.app_paths import config_dir
from src.bilibili_client import BilibiliClient
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

SOURCE_ID = "DS-9"
OUTPUT_PATH = DATA_DIR / "output" / "ds9_latest.json"
CONFIG_FILE = config_dir() / "topic_tags.txt"
CONTAINER_PLACEHOLDER = "topic://tags"
TOPIC_MAX_PAGES = 3


def _read_tags() -> list[str]:
    """读取话题名列表（去重、去空行）。"""
    if not CONFIG_FILE.exists():
        return []
    tags: list[str] = []
    seen: set[str] = set()
    for line in CONFIG_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        tag = line.strip()
        if tag and tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tags


def _extract_dynamic_ids(data: dict) -> list[str]:
    """从话题接口 data 中宽松提取动态 ID（兼容 cards/items/hot_list 结构，去重保序）。"""
    ids: list[str] = []
    seen: set[str] = set()
    for key in ("cards", "items", "hot_list"):
        for entry in data.get(key) or []:
            if not isinstance(entry, dict):
                continue
            desc = entry.get("desc") or {}
            raw = (
                desc.get("dynamic_id")
                or entry.get("id_str")
                or entry.get("dynamic_id")
                or (entry.get("item") or {}).get("id_str")
            )
            if raw is None:
                continue
            dynamic_id = normalize_dynamic_id(str(raw))
            if dynamic_id and dynamic_id not in seen:
                seen.add(dynamic_id)
                ids.append(dynamic_id)
    return ids


def _fingerprint(tags: list[str], latest_by_tag: dict[str, list[str]]) -> str:
    """增量指纹：话题名 + 每话题最新一页动态 id 集合的 sha256。

    话题顺序与每话题内 id 顺序均规范化（排序），仅内容变化才改变指纹。
    """
    canonical = {tag: sorted(ids) for tag, ids in latest_by_tag.items()}
    text = json.dumps(canonical, sort_keys=True, ensure_ascii=False)
    return fingerprint_of_text(text)


def check_update(*, force: bool = False) -> CheckResult:
    tags = _read_tags()
    if not tags:
        prev_output = load_previous_output(OUTPUT_PATH)
        return CheckResult(
            source_id=SOURCE_ID,
            updated=False,
            container_url=CONTAINER_PLACEHOLDER,
            container_id="",
            title="话题源（未配置）",
            published_at=0,
            previous_container_url=CONTAINER_PLACEHOLDER,
            activity_links=(prev_output or {}).get("activity_links") or [],
            checked_at=int(time.time()),
        )

    now = int(time.time())
    latest_by_tag: dict[str, list[str]] = {}
    raw_ids: list[str] = []
    fp: str | None = None
    prev_fp = load_source_fingerprint(SOURCE_ID)
    with BilibiliClient() as client:
        for tag in tags:
            data = client.get_topic_new(tag) or {}
            latest_ids = _extract_dynamic_ids(data)
            latest_by_tag[tag] = latest_ids
            raw_ids.extend(latest_ids)
        fp = _fingerprint(tags, latest_by_tag)
        if force or fp != prev_fp:
            # 内容变化/强制：才需要多页历史
            for tag in tags:
                offset = ""
                for _ in range(TOPIC_MAX_PAGES):
                    page = client.get_topic_history(tag, offset_dynamic_id=offset)
                    if not page:
                        break
                    ids = _extract_dynamic_ids(page)
                    if not ids:
                        break
                    raw_ids.extend(ids)
                    next_offset = str(page.get("offset") or "")
                    if not next_offset:
                        break
                    offset = next_offset

    seen: set[str] = set()
    links: list[str] = []
    for did in raw_ids:
        if did in seen:
            continue
        seen.add(did)
        links.append(opus_link(did))

    if not links:
        prev_output = load_previous_output(OUTPUT_PATH)
        return CheckResult(
            source_id=SOURCE_ID,
            updated=False,
            container_url=CONTAINER_PLACEHOLDER,
            container_id="",
            title="话题源（无动态）",
            published_at=0,
            previous_container_url=CONTAINER_PLACEHOLDER,
            activity_links=(prev_output or {}).get("activity_links") or [],
            checked_at=now,
        )
    if not force and fp == prev_fp:
        # 最新页与上次成功处理的批次相同：无新内容
        prev_output = load_previous_output(OUTPUT_PATH)
        return CheckResult(
            source_id=SOURCE_ID,
            updated=False,
            container_url=CONTAINER_PLACEHOLDER,
            container_id="tags",
            title=f"话题源（{len(tags)} 个话题，{len(links)} 条动态）",
            published_at=0,
            previous_container_url=CONTAINER_PLACEHOLDER,
            activity_links=(prev_output or {}).get("activity_links") or [],
            checked_at=now,
        )
    return CheckResult(
        source_id=SOURCE_ID,
        updated=True,
        container_url=CONTAINER_PLACEHOLDER,
        container_id="tags",
        title=f"话题源（{len(tags)} 个话题，{len(links)} 条动态）",
        published_at=now,
        previous_container_url=CONTAINER_PLACEHOLDER,
        activity_links=links,
        checked_at=now,
        cv_id=fp,  # 复用 cv_id 承载 fingerprint，由 commit_source_checkpoint 持久化
    )


def save_result(result: CheckResult) -> Path | None:
    return write_result(OUTPUT_PATH, result)
