"""清理动态与取关（源自 LAS lib/clear.js）。

清理策略（与 Binggo 的"抽奖临时关注"分区联动）：
1. 删除自己空间里超过 max_days 天的**由 Binggo 创建的**转发动态（可选）；
2. 对"抽奖临时关注"分区内的用户批量取关（白名单排除）。

安全不变量（P0）：
- **只删除本地参与台账（participation_actions）中确认由 Binggo 成功转发
  （repost ok=True 且状态 joined）的动态**；无法确认归属的一律跳过，
  绝不只凭"是转发 + 超期"删除用户手动转发的内容。
- 动态作者在白名单（white_list）中的同样跳过（白名单同时保护删除与取关）。
- `dry_run` 默认 True：真实删除必须显式传 False。

全部为静默容错：单个删除/取关失败不影响其余。
"""
from __future__ import annotations

import json
import time
from typing import Any

from src.bilibili_client import BilibiliClient

DEFAULT_MAX_DAYS = 30
DEFAULT_PARTITION_NAME = "抽奖临时关注"


def _owned_repost_dynamic_ids() -> frozenset[str]:
    """收集 Binggo **真实创建**的转发动态 ID（归属台账）。

    判定：当前 uid 的 participation_actions 中存在该动态记录，
    且 status == "joined"、actions_json 中 repost 动作 ok=True，
    且 repost 的 detail **不含"已转发"**（Binggo 本次真实 POST 创建了新转发；
    若参与前探测到用户已手动转发，repost 会记 ok=True 但 detail 为"已转发"，
    那条转发并非 Binggo 创建，不得纳入可删除集合）。
    任何异常或无法确认时返回空集 —— **宁可不删，不可误删**。
    """
    try:
        from sqlmodel import select

        from src.db.models import ParticipationActionRow
        from src.db.session import session_scope
        from src.db.uids import participation_uid

        uid = participation_uid()
        if not uid:
            return frozenset()
        owned: set[str] = set()
        with session_scope() as session:
            rows = session.exec(
                select(ParticipationActionRow).where(
                    ParticipationActionRow.uid == uid,
                    ParticipationActionRow.status == "joined",
                )
            ).all()
            # 注意：必须在 session 存活期间读取字段（块外访问会触发
            # DetachedInstanceError，被外层 except 吞掉导致整个函数静默返回空集）
            for row in rows:
                if not row.dynamic_id:
                    continue
                try:
                    actions = json.loads(row.actions_json or "[]")
                except ValueError:
                    actions = []
                if any(
                    isinstance(a, dict)
                    and a.get("action") == "repost"
                    and a.get("ok")
                    and "已转发" not in str(a.get("detail") or "")
                    for a in actions
                ):
                    owned.add(str(row.dynamic_id))
        return frozenset(owned)
    except Exception:
        return frozenset()


def _item_dynamic_id(item: dict) -> str:
    """转发动态自身的 id（删除接口用；space feed 中每一条都是独立动态）。"""
    return str(item.get("id_str") or "")


def _item_source_dynamic_id(item: dict) -> str:
    """转发所指向的源动态 id（归属台账用）。

    兼容新版 polymer API（desc.rid / origin 嵌套）与旧版 feed（item.orig）。
    取不到返回空串——归属校验会因此跳过该条（宁可不删，不可误删）。
    """
    modules = item.get("modules") or {}
    if isinstance(modules, list):
        modules = modules[0] if modules else {}
    if isinstance(modules, dict):
        dynamic = modules.get("module_dynamic") or {}
        if isinstance(dynamic, dict):
            desc = dynamic.get("desc") or {}
            if isinstance(desc, dict):
                rid = str(desc.get("rid") or "").strip()
                if rid:
                    return rid
            origin = dynamic.get("origin") or {}
            if isinstance(origin, dict):
                origin_desc = origin.get("desc") or {}
                if isinstance(origin_desc, dict):
                    rid = str(origin_desc.get("dynamic_id") or "").strip()
                    if rid:
                        return rid
                rid = str(origin.get("id_str") or "").strip()
                if rid:
                    return rid
    orig = item.get("orig") or {}
    if isinstance(orig, dict):
        return str(orig.get("id_str") or "").strip()
    return ""


def _item_source_author_uid(item: dict) -> int | None:
    """转发源动态的作者 mid（白名单保护用）；解析失败返回 None。"""
    modules = item.get("modules") or {}
    if isinstance(modules, list):
        modules = modules[0] if modules else {}
    if isinstance(modules, dict):
        dynamic = modules.get("module_dynamic") or {}
        if isinstance(dynamic, dict):
            origin = dynamic.get("origin") or {}
            if isinstance(origin, dict):
                origin_modules = origin.get("modules") or {}
                if isinstance(origin_modules, list):
                    origin_modules = origin_modules[0] if origin_modules else {}
                if isinstance(origin_modules, dict):
                    author = origin_modules.get("module_author") or {}
                    if isinstance(author, dict):
                        try:
                            value = int(author.get("mid") or 0)
                            if value:
                                return value
                        except (TypeError, ValueError):
                            pass
    orig = item.get("orig") or {}
    if isinstance(orig, dict):
        try:
            value = int(orig.get("uid") or 0)
            if value:
                return value
        except (TypeError, ValueError):
            pass
    return None


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
    dry_run: bool = True,
) -> dict[str, Any]:
    """清理超期转发动态（仅限 Binggo 创建）与取关。

    dry_run 默认 True：真实删除/取关必须显式传 dry_run=False。
    返回键：scanned / deleted / unfollowed / skipped / skipped_unowned /
    skipped_whitelist。
    """
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
        "skipped_unowned": 0,
        "skipped_whitelist": 0,
    }

    # 1) 删除超期转发动态（仅限 Binggo 归属台账内的动态）
    if delete_dynamic:
        owned_ids = _owned_repost_dynamic_ids()
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
                source_id = _item_source_dynamic_id(item)
                if not source_id or source_id not in owned_ids:
                    # 归属校验：非 Binggo 创建的转发绝不删除（含用户手动转发）
                    result["skipped_unowned"] += 1
                    result["skipped"] += 1
                    continue
                author_uid = _item_source_author_uid(item)
                if author_uid is not None and author_uid in white_uids:
                    # 白名单同时保护删除与取关（按源动态作者匹配）
                    result["skipped_whitelist"] += 1
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
