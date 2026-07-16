"""将 6 个数据源 state 中的「上次专栏/视频」回退为上上个，便于重新触发一键更新流水线。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.bilibili_client import BilibiliClient
from src.sources.common import opus_link
from src.state_store import get_last_container, set_last_container

SOURCES = {
    "DS-1": {"mid": 885439, "type": "video"},
    "DS-2": {"mid": 3546836235193146, "type": "article"},
    "DS-3": {"mid": 100680137, "type": "article"},
    "DS-4": {"mid": 126038161, "type": "article"},
    "DS-5": {"mid": 3546776042736296, "type": "opus"},
    "DS-6": {"mid": 492426375, "type": "opus"},
}


def article_url(cv_id: int | str) -> str:
    return f"https://www.bilibili.com/read/cv{cv_id}"


def video_url(bvid: str) -> str:
    return f"https://www.bilibili.com/video/{bvid}"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    with BilibiliClient() as client:
        for source_id, cfg in SOURCES.items():
            previous = get_last_container(source_id)
            mid = int(cfg["mid"])
            kind = str(cfg["type"])

            if kind == "video":
                referer = f"https://space.bilibili.com/{mid}/video"
                data = client.get_json(
                    "https://api.bilibili.com/x/space/wbi/arc/search",
                    params={
                        "mid": mid,
                        "pn": 1,
                        "ps": 2,
                        "tid": 0,
                        "order": "pubdate",
                        "platform": "web",
                    },
                    wbi=True,
                    referer=referer,
                )
                vlist = (data.get("data") or {}).get("list", {}).get("vlist") or []
                if len(vlist) < 2:
                    raise RuntimeError(f"{source_id}: 视频不足 2 条")
                item = vlist[1]
                bvid = str(item["bvid"])
                set_last_container(
                    source_id,
                    video_url(bvid),
                    container_id=bvid,
                    title=str(item.get("title") or ""),
                )
                print(f"{source_id}:\n  原: {previous}\n  新: {video_url(bvid)} — {item.get('title', '')}")
                continue

            articles = client.get_recent_articles(mid, limit=2)
            if len(articles) < 2:
                raise RuntimeError(f"{source_id}: 专栏不足 2 篇")
            item = articles[1]
            cv_id = int(item["id"])
            title = str(item.get("title") or "")

            if kind == "article":
                set_last_container(
                    source_id,
                    article_url(cv_id),
                    container_id=str(cv_id),
                    title=title,
                )
                print(f"{source_id}:\n  原: {previous}\n  新: {article_url(cv_id)} — {title}")
                continue

            detail = client.get_article_detail(cv_id)
            opus = detail.get("opus") or {}
            opus_id = str(opus.get("opus_id") or "")
            if not opus_id:
                raise RuntimeError(f"{source_id}: cv{cv_id} 无 opus_id")
            url = opus_link(opus_id)
            set_last_container(
                source_id,
                url,
                container_id=opus_id,
                title=title,
                cv_id=str(cv_id),
            )
            print(f"{source_id}:\n  原: {previous}\n  新: {url} (cv{cv_id}) — {title}")

    print("--- 6 个数据源均已回退到上上个专栏/视频 ---")


if __name__ == "__main__":
    main()
