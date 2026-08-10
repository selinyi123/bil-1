"""清理动态与取关（源自 LAS lib/clear.js）。

清理策略（与 Binggo 的"抽奖临时关注"分区联动）：
1. 删除自己空间里超过 max_days 天的转发动态（可选）；
2. 对"抽奖临时关注"分区内的用户批量取关（白名单排除）。

全部为静默容错：单个删除/取关失败不影响其余。
"""
from __future__ import annotations

import time
from typing import Any

from src.bilibili_client import BilibiliClient

DEFAULT_MAX_DAYS = 30
DEFAULT_PARTITION_NAME = "抽奖临时关注"


def _item_dynamic_id(item: dict) -> str:
    return str(item.get("id_str") or "")


def _item_is_repost(item: dict) -> bool:
    """仅当动态为「转发」（desc.type == 1）时才可删除，原创动态绝不删。"""
    modules = item.get("modules") or {}
    if isinstance(modules, list):
        modules = modules[0] if modules else {}
    if not isinstance(modules, dict):
        return False
    dynamic = modules.get("module_dynamic") or {}
    if not isinstance(dynamic, dict):
        return False
    desc = dynamic.get("desc") or {}
    if not isinstance(desc, dict):
        return False
    try:
        return int(desc.get("type") or 0) == 1
    except (TypeError, ValueError):
        return False


def _item_pub_ts(item: dict) -> int:
    modules = item.get("modules") or {}
    if isinstance(modules, list):
        modules = modules[0] if modules else {}
    if not isinstance(modules, dict):
        return 0
    author = modules.get("module_author") or {}
    if not isinstance(author, dict):
        return 0
    try:
        value = int(author.get("pub_ts") or 0)
        return value or 0
    except (TypeError, ValueError):
        return 0


def clear_follows(
    client: BilibiliClient,
    *,
    max_days: int = DEFAULT_MAX_DAYS,
    delete_dynamic: bool = True,
    white_list: str = "",
    partition_name: str = DEFAULT_PARTITION_NAME,
    dry_run: bool = False,
) -> dict[str, Any]:
    # 防御：max_days 下限 1 天，避免 0/负数导致全量删除
    try:
        max_days = max(1, int(max_days))
    except (TypeError, ValueError):
        max_days = DEFAULT_MAX_DAYS
    now = int(time.time())
    white_uids = {
        int(part) for part in str(white_list or "").split(",") if part.strip().isdigit()
    }
    result: dict[str, Any] = {
        "scanned": 0,
        "deleted": 0,
        "unfollowed": 0,
        "skipped": 0,
    }

    # 1) 删除超期转发动态
    if delete_dynamic:
        offset = ""
        for _ in range(20):
            data = client.get_my_space_feed(offset)
            if not data:
                break
            items = data.get("items") or []
            if not isinstance(items, list):
                break
            result["scanned"] += len(items)
            for item in items:
                if not isinstance(item, dict):
                    continue
                dynamic_id = _item_dynamic_id(item)
                pub_ts = _item_pub_ts(item)
                if not dynamic_id or not pub_ts:
                    result["skipped"] += 1
                    continue
                if not _item_is_repost(item):
                    # 只清理转发的抽奖动态，原创动态一律跳过
                    result["skipped"] += 1
                    continue
                if now - pub_ts > max_days * 86400:
                    if dry_run or client.delete_dynamic(dynamic_id):
                        result["deleted"] += 1
                else:
                    result["skipped"] += 1
            if not data.get("has_more"):
                break
            offset = str(data.get("offset") or "")
            if not offset:
                break

    # 2) 分区批量取关
    for tag in client.get_relation_tags() or []:
        if not isinstance(tag, dict):
            continue
        if str(tag.get("name")) != partition_name:
            continue
        try:
            tagid = int(tag.get("tagid"))
        except (TypeError, ValueError):
            continue
        for pn in range(1, 101):
            uids = client.get_partition_uids(tagid, pn=pn)
            if not uids:
                break
            for uid in uids:
                if uid in white_uids:
                    result["skipped"] += 1
                    continue
                if dry_run or client.cancel_attention(uid):
                    result["unfollowed"] += 1
            if len(uids) < 50:
                break

    return result
