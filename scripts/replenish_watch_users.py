"""从转发池补齐 watch 用户至 30 人（following >= 1000）。"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.bilibili_client import BilibiliClient
from src.sources.common import load_previous_output, normalize_activity_id
from src.state_store import DATA_DIR
from src.watch_feed import SPACE_FEED_URL, extract_forward_orig_id

CANDIDATES_PATH = ROOT / "config" / "watch_users_candidates.json"
REACTION_URL = "https://api.bilibili.com/x/polymer/web-dynamic/v1/detail/reaction"
STAT_URL = "https://api.bilibili.com/x/relation/stat"
MIN_FOLLOWING = 1000
TARGET_COUNT = 30

SOURCE_FILES = tuple(
    DATA_DIR / "output" / f"ds{i}_latest.json" for i in range(1, 7)
)


def collect_lottery_ids(limit: int = 50) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for path in SOURCE_FILES:
        payload = load_previous_output(path) or {}
        for url in payload.get("activity_links") or []:
            dynamic_id = normalize_activity_id(str(url))
            if dynamic_id and dynamic_id not in seen:
                seen.add(dynamic_id)
                ids.append(dynamic_id)
                if len(ids) >= limit:
                    return ids
    return ids


def fetch_forward_users(client: BilibiliClient, dynamic_id: str, *, max_pages: int = 4) -> list[dict]:
    referer = f"https://www.bilibili.com/opus/{dynamic_id}"
    offset = ""
    users: list[dict] = []
    for _ in range(max_pages):
        data = client.get_json(
            REACTION_URL,
            params={"id": dynamic_id, "action_type": 2, "offset": offset},
            referer=referer,
            retries=2,
        )
        payload = data.get("data") or {}
        for item in payload.get("items") or []:
            mid = int(item.get("mid") or 0)
            if mid > 0:
                users.append({"mid": mid, "name": str(item.get("name") or mid)})
        if not payload.get("has_more"):
            break
        offset = str(payload.get("offset") or "")
        if not offset:
            break
        time.sleep(0.15)
    return users


def fetch_following(client: BilibiliClient, mid: int) -> int:
    data = client.get_json(
        STAT_URL,
        params={"vmid": mid},
        referer=f"https://space.bilibili.com/{mid}",
        retries=2,
    )
    return int((data.get("data") or {}).get("following") or 0)


def fetch_follower(client: BilibiliClient, mid: int) -> int:
    data = client.get_json(
        STAT_URL,
        params={"vmid": mid},
        referer=f"https://space.bilibili.com/{mid}",
        retries=2,
    )
    return int((data.get("data") or {}).get("follower") or 0)


def forward_ratio(client: BilibiliClient, mid: int) -> float:
    referer = f"https://space.bilibili.com/{mid}/dynamic"
    try:
        data = client.get_json(
            SPACE_FEED_URL,
            params={
                "host_mid": mid,
                "offset": "",
                "type": "all",
                "timezone_offset": -480,
                "platform": "web",
                "web_location": "333.1365",
            },
            referer=referer,
            wbi=True,
            retries=2,
        )
    except Exception:
        return 0.0
    items = (data.get("data") or {}).get("items") or []
    sample = items[:25]
    if not sample:
        return 0.0
    return round(sum(1 for item in sample if extract_forward_orig_id(item)) / len(sample), 2)


def main() -> int:
    payload = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
    existing = payload.get("users") or []
    existing_mids = {int(u["mid"]) for u in existing}
    need = TARGET_COUNT - len(existing)
    if need <= 0:
        print(f"已有 {len(existing)} 人，无需补齐")
        return 0

    print(f"当前 {len(existing)} 人，需补 {need} 人", flush=True)
    lottery_ids = collect_lottery_ids(50)
    hit_counter: Counter[int] = Counter()
    names: dict[int, str] = {}

    with BilibiliClient(timeout=30.0) as client:
        for index, dynamic_id in enumerate(lottery_ids, start=1):
            try:
                users = fetch_forward_users(client, dynamic_id, max_pages=4)
            except Exception as exc:
                print(f"[{index}] skip {dynamic_id}: {exc}", flush=True)
                time.sleep(0.5)
                continue
            for user in users:
                mid = int(user["mid"])
                hit_counter[mid] += 1
                names[mid] = user["name"]
            if index % 10 == 0:
                print(f"[{index}/{len(lottery_ids)}] pool={len(hit_counter)}", flush=True)
            time.sleep(0.2)

        added: list[dict] = []
        for mid, hit_count in hit_counter.most_common():
            if mid in existing_mids:
                continue
            if hit_count < 2:
                break
            following = fetch_following(client, mid)
            if following < MIN_FOLLOWING:
                continue
            ratio = forward_ratio(client, mid)
            if ratio < 0.5:
                continue
            follower = fetch_follower(client, mid)
            row = {
                "mid": mid,
                "name": names.get(mid, str(mid)),
                "hit_count": hit_count,
                "forward_ratio": ratio,
                "score": hit_count * 2 + round(ratio * 3),
                "following": following,
                "follower": follower,
            }
            added.append(row)
            print(
                f"+ {row['name']} mid={mid} following={following} hits={hit_count} ratio={ratio}",
                flush=True,
            )
            if len(added) >= need:
                break
            time.sleep(0.25)

    if len(added) < need:
        print(f"警告：仅补到 {len(added)} 人（目标 {need}）", flush=True)

    merged = existing + added
    merged.sort(key=lambda item: (-item["score"], -item["hit_count"], item["mid"]))
    payload["users"] = merged[:TARGET_COUNT]
    payload["filtered_count"] = len(payload["users"])
    payload["filter"] = f"following >= {MIN_FOLLOWING}"
    payload["replenished_at"] = int(time.time())
    payload["replenished_users"] = added
    CANDIDATES_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"完成：共 {len(payload['users'])} 人 → {CANDIDATES_PATH}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
