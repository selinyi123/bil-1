from __future__ import annotations

import re
import time
from pathlib import Path

from src.bilibili_client import BilibiliClient
from src.sources.common import (
    CheckResult,
    extract_opus_links_with_hints,
    load_previous_output,
    save_result as write_result,
)
from src.state_store import DATA_DIR, get_last_container, set_last_container

SOURCE_ID = "DS-4"
MID = 126038161
OUTPUT_PATH = DATA_DIR / "output" / "ds4_latest.json"

EXCLUDE_LINK_TEXT_RE = re.compile(r"抽奖黑幕|曝光|弹幕视频网|QQ群|大会员")


def article_url(cv_id: int | str) -> str:
    return f"https://www.bilibili.com/read/cv{cv_id}"


def check_update(*, force: bool = False) -> CheckResult:
    with BilibiliClient() as client:
        latest = client.get_latest_article(MID)
        cv_id = int(latest["id"])
        container_url = article_url(cv_id)
        previous = get_last_container(SOURCE_ID)

        if not force and previous == container_url:
            prev_output = load_previous_output(OUTPUT_PATH)
            return CheckResult(
                source_id=SOURCE_ID,
                updated=False,
                container_url=container_url,
                container_id=str(cv_id),
                title=latest.get("title", ""),
                published_at=int(latest.get("publish_time") or 0),
                previous_container_url=previous,
                activity_links=(prev_output or {}).get("activity_links") or [],
                checked_at=int(time.time()),
                link_hints=(prev_output or {}).get("link_hints") or {},
            )

        detail = client.get_article_detail(cv_id)
        links, hints = extract_opus_links_with_hints(
            detail,
            exclude_link_text=EXCLUDE_LINK_TEXT_RE,
            default_hint="互动抽奖",
        )

        set_last_container(
            SOURCE_ID,
            container_url,
            container_id=str(cv_id),
            title=detail.get("title") or latest.get("title", ""),
        )

        return CheckResult(
            source_id=SOURCE_ID,
            updated=True,
            container_url=container_url,
            container_id=str(cv_id),
            title=detail.get("title") or latest.get("title", ""),
            published_at=int(detail.get("publish_time") or latest.get("publish_time") or 0),
            previous_container_url=previous,
            activity_links=links,
            checked_at=int(time.time()),
            link_hints=hints,
        )


def save_result(result: CheckResult) -> Path | None:
    return write_result(OUTPUT_PATH, result)
