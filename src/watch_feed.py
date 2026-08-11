from __future__ import annotations

import time
from dataclasses import dataclass

from src.bilibili_client import BilibiliClient, api_code
from src.sources.common import is_valid_dynamic_id, normalize_activity_id, opus_link

SPACE_FEED_URL = "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space"
FEED_PAGE_SIZE = 20
DEFAULT_MAX_PAGES = 30
PAGE_RETRY_ATTEMPTS = 4
PAGE_RETRY_BASE_DELAY = 1.0
PAGE_REQUEST_DELAY = 0.22


@dataclass(frozen=True, slots=True)
class ForwardLink:
    dynamic_id: str
    url: str
    pub_ts: int
    forward_id: str


def extract_forward_orig_id(item: dict) -> str | None:
    """从空间动态 feed 条目中提取转发原动态的 id_str。"""
    if item.get("type") != "DYNAMIC_TYPE_FORWARD":
        return None
    orig = item.get("orig") or {}
    id_str = str(orig.get("id_str") or "").strip()
    if id_str and is_valid_dynamic_id(id_str):
        return id_str
    return None


def extract_feed_pub_ts(item: dict) -> int | None:
    modules = item.get("modules")
    pub_ts: object = None
    if isinstance(modules, dict):
        pub_ts = (modules.get("module_author") or {}).get("pub_ts")
    elif isinstance(modules, list):
        for module in modules:
            if not isinstance(module, dict):
                continue
            if module.get("module_type") == "MODULE_TYPE_AUTHOR":
                pub_ts = (module.get("module_author") or {}).get("pub_ts")
                break
    if pub_ts is None:
        return None
    try:
        value = int(pub_ts)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def extract_forward_id(item: dict) -> str:
    return str(item.get("id_str") or "").strip()


def _fetch_space_feed_page(
    client: BilibiliClient,
    *,
    mid: int,
    offset: str,
) -> dict:
    referer = f"https://space.bilibili.com/{mid}/dynamic"
    last_error: Exception | None = None
    for attempt in range(PAGE_RETRY_ATTEMPTS):
        try:
            payload = client.get_json(
                SPACE_FEED_URL,
                params={
                    "host_mid": mid,
                    "offset": offset,
                    "type": "all",
                    "timezone_offset": -480,
                    "platform": "web",
                    "web_location": "333.1365",
                },
                referer=referer,
                wbi=True,
                retries=1,
            )
            if api_code(payload) != 0:
                message = str(payload.get("message") or "未知错误")
                raise RuntimeError(f"API error {payload.get('code')}: {message}")
            data = payload.get("data")
            if not isinstance(data, dict):
                raise RuntimeError("空间动态响应缺少 data")
            return data
        except Exception as exc:
            last_error = exc
            if attempt < PAGE_RETRY_ATTEMPTS - 1:
                time.sleep(PAGE_RETRY_BASE_DELAY * (attempt + 1))
                continue
            raise RuntimeError(f"拉取空间动态失败: {exc}") from exc
    if last_error:
        raise RuntimeError(f"拉取空间动态失败: {last_error}") from last_error
    raise RuntimeError("拉取空间动态失败")


def collect_forward_links_for_user(
    client: BilibiliClient,
    mid: int,
    *,
    since_ts: int,
    until_ts: int | None = None,
    max_pages: int = DEFAULT_MAX_PAGES,
    stats: dict | None = None,
) -> list[ForwardLink]:
    """扫描单个用户在时间窗口内的转发原动态（仅 DYNAMIC_TYPE_FORWARD）。

    stats（可选）传入 dict 时记录 `skipped_no_pub_ts`：pub_ts 缺失而无法
    判定是否落在时间窗口内的条目数（这些条目不收集、不伪造时间戳）。
    """
    upper = int(until_ts if until_ts is not None else time.time())
    lower = int(since_ts)
    if lower > upper:
        return []

    offset = ""
    collected: list[ForwardLink] = []
    seen_dynamic: set[str] = set()
    skipped_no_ts = 0

    for _ in range(max(1, max_pages)):
        data = _fetch_space_feed_page(client, mid=mid, offset=offset)
        items = data.get("items") or []
        if not items:
            break

        reached_older = False
        for item in items:
            if not isinstance(item, dict):
                continue
            pub_ts = extract_feed_pub_ts(item)
            if pub_ts is None:
                # 无法判定时间窗口：不收集、不伪造时间戳，计入跳过计数
                skipped_no_ts += 1
                continue
            if pub_ts > upper:
                continue
            if pub_ts < lower:
                reached_older = True
                continue

            dynamic_id = extract_forward_orig_id(item)
            if not dynamic_id or dynamic_id in seen_dynamic:
                continue
            seen_dynamic.add(dynamic_id)
            collected.append(
                ForwardLink(
                    dynamic_id=dynamic_id,
                    url=opus_link(dynamic_id),
                    pub_ts=pub_ts,
                    forward_id=extract_forward_id(item),
                )
            )

        if reached_older:
            break

        next_offset = str(data.get("offset") or "")
        if not next_offset or len(items) < FEED_PAGE_SIZE:
            break
        offset = next_offset
        time.sleep(PAGE_REQUEST_DELAY)

    if stats is not None:
        stats["skipped_no_pub_ts"] = skipped_no_ts

    return collected
