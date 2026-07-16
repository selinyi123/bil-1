from __future__ import annotations

import time
from pathlib import Path

from src.bilibili_client import BilibiliClient
from src.sources.common import (
    CheckResult,
    extract_opus_links_with_hints,
    load_previous_output,
    opus_link,
    save_result as write_result,
)
from src.state_store import DATA_DIR, get_last_container, get_last_cv_id, set_last_container

SOURCE_ID = "DS-5"
MID = 3546776042736296
OUTPUT_PATH = DATA_DIR / "output" / "ds5_latest.json"


def check_update(*, force: bool = False) -> CheckResult:
    with BilibiliClient() as client:
        latest = client.get_latest_article(MID)
        cv_id = int(latest["id"])
        previous = get_last_container(SOURCE_ID)
        previous_cv = get_last_cv_id(SOURCE_ID)

        if not force and previous_cv == str(cv_id) and previous:
            prev_output = load_previous_output(OUTPUT_PATH)
            return CheckResult(
                source_id=SOURCE_ID,
                updated=False,
                container_url=previous,
                container_id=(prev_output or {}).get("container_id") or "",
                title=latest.get("title", ""),
                published_at=int(latest.get("publish_time") or 0),
                previous_container_url=previous,
                activity_links=(prev_output or {}).get("activity_links") or [],
                checked_at=int(time.time()),
                link_hints=(prev_output or {}).get("link_hints") or {},
            )

        detail = client.get_article_detail(cv_id)
        opus = detail.get("opus") or {}
        container_opus_id = str(opus.get("opus_id") or "")
        if not container_opus_id:
            raise RuntimeError("无法从最新内容解析 Opus 容器 ID")

        container_url = opus_link(container_opus_id)
        links, hints = extract_opus_links_with_hints(
            detail,
            container_opus_id=container_opus_id,
        )

        set_last_container(
            SOURCE_ID,
            container_url,
            container_id=container_opus_id,
            title=detail.get("title") or latest.get("title", ""),
            cv_id=str(cv_id),
        )

        return CheckResult(
            source_id=SOURCE_ID,
            updated=True,
            container_url=container_url,
            container_id=container_opus_id,
            title=detail.get("title") or latest.get("title", ""),
            published_at=int(detail.get("publish_time") or latest.get("publish_time") or 0),
            previous_container_url=previous,
            activity_links=links,
            checked_at=int(time.time()),
            link_hints=hints,
        )


def save_result(result: CheckResult) -> Path | None:
    return write_result(OUTPUT_PATH, result)
