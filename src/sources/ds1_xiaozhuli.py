from __future__ import annotations

import json
import re
import time
from pathlib import Path

from src.bilibili_client import BilibiliClient
from src.sources.common import (
    CheckResult,
    extract_opus_links_with_hints,
    load_previous_output,
    normalize_activity_id,
    save_result as write_result,
)
from src.state_store import DATA_DIR, get_last_container, set_last_container

SOURCE_ID = "DS-1"
MID = 885439
OUTPUT_PATH = DATA_DIR / "output" / "ds1_latest.json"

ACTIVITY_LINK_RE = re.compile(r"https://t\.bilibili\.com/\d{19}")


def video_url(bvid: str) -> str:
    return f"https://www.bilibili.com/video/{bvid}"


def extract_activity_links(desc: str) -> list[str]:
    """从视频简介提取去重后的活动链接（保持 t.bilibili.com 原样）。"""
    return list(dict.fromkeys(ACTIVITY_LINK_RE.findall(desc or "")))


def check_update(*, force: bool = False) -> CheckResult:
    with BilibiliClient() as client:
        latest = client.get_latest_video(MID)
        bvid = latest["bvid"]
        container_url = video_url(bvid)
        previous = get_last_container(SOURCE_ID)

        if not force and previous == container_url:
            prev_output = load_previous_output(OUTPUT_PATH)
            return CheckResult(
                source_id=SOURCE_ID,
                updated=False,
                container_url=container_url,
                container_id=bvid,
                title=latest.get("title", ""),
                published_at=int(latest.get("created") or 0),
                previous_container_url=previous,
                activity_links=(prev_output or {}).get("activity_links") or [],
                checked_at=int(time.time()),
                link_hints=(prev_output or {}).get("link_hints") or {},
            )

        detail = client.get_video_detail(bvid)
        desc = detail.get("desc") or ""
        links = extract_activity_links(desc)
        hints = {
            activity_id: "互动抽奖"
            for url in links
            if (activity_id := normalize_activity_id(url))
        }

        set_last_container(
            SOURCE_ID,
            container_url,
            container_id=bvid,
            title=detail.get("title") or latest.get("title", ""),
        )

        return CheckResult(
            source_id=SOURCE_ID,
            updated=True,
            container_url=container_url,
            container_id=bvid,
            title=detail.get("title") or latest.get("title", ""),
            published_at=int(detail.get("pubdate") or latest.get("created") or 0),
            previous_container_url=previous,
            activity_links=links,
            checked_at=int(time.time()),
            link_hints=hints,
        )


def save_result(result: CheckResult) -> Path | None:
    return write_result(OUTPUT_PATH, result)
