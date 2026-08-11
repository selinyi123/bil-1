"""清理动态与取关（源自 LAS lib/clear.js）。

清理策略（与 Binggo 参与增强配置的关注分区联动）：
1. 删除自己空间里超过 max_days 天的**由 Binggo 创建的**转发动态（可选）；
2. 对当前参与增强配置使用的关注分区内用户批量取关（白名单排除）。

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


def _owned_repost_dynamic_ids() -> tuple[frozenset[str], frozenset[str]]:
    """收集 Binggo **真实创建**的转发动态 ID（归属台账，exact ownership）。

    返回 (exact_ids, legacy_source_ids)：
    - exact_ids：repost 成功且 **记录了 extra.created_dynamic_id**（repost API
      返回的真实新转发动态 id）→ cleanup 只精确匹配 feed 中该 id 的转发；
    - legacy_source_ids：**旧版记录**（迁移前无 created id）中 repost 成功且
      detail 不含"已转发"的源动态 id → 兼容旧记录按源 id 匹配。
    任何异常或无法确认时返回空集 —— **宁可不删，不可误删**。
    """
    try:
        from sqlmodel import select

        from src.db.models import ParticipationActionRow
        from src.db.session import session_scope
        from src.db.uids import participation_uid

        uid = participation_uid()
        if not uid:
            return frozenset(), frozenset()
        exact: set[str] = set()
        legacy_sources: set[str] = set()
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
                has_created_id = False
                reposted_new = False
                for a in actions:
                    if not (
                        isinstance(a, dict)
                        and a.get("action") == "repost"
                        and a.get("ok")
                        and "已转发" not in str(a.get("detail") or "")
                    ):
                        continue
                    extra = a.get("extra")
                    if isinstance(extra, dict):
                        created_id = str(extra.get("created_dynamic_id") or "").strip()
                        if created_id:
                            exact.add(created_id)
                            has_created_id = True
                            continue
                    reposted_new = True
                if not has_created_id and reposted_new:
                    # 旧记录（无 created id）：按源动态 id 兼容匹配
                    legacy_sources.add(str(row.dynamic_id))
        return frozenset(exact), frozenset(legacy_sources)
    except Exception:
        return frozenset(), frozenset()


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


def _resolve_partition_name(partition_name: str | None) -> str:
    """解析清理使用的分区名。

    `partition_name` 未显式提供（None/空）时，自动沿用 participate_enhance.json
    中已启用的 partition.name；显式提供的值（含默认分区名）原样使用，不被
    配置重定向。配置读取失败时 fail-soft 回退默认名。
    """
    if partition_name is not None and str(partition_name).strip():
        # 显式指定（含显式传默认名）：以调用方为准，不咨询配置
        return str(partition_name).strip()
    try:
        from src.participate_enhance import load_participate_enhance

        partition = load_participate_enhance().get("partition") or {}
        if isinstance(partition, dict) and partition.get("enabled"):
            configured = str(partition.get("name") or "").strip()
            if configured:
                return configured
    except (OSError, ValueError, TypeError):
        pass
    return DEFAULT_PARTITION_NAME


def clear_follows(
    client: BilibiliClient,
    *,
    max_days: int = DEFAULT_MAX_DAYS,
    delete_dynamic: bool = True,
    white_list: str = "",
    partition_name: str | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """清理超期转发动态（仅限 Binggo 创建）与关注分区。

    dry_run 默认 True：真实删除/取关必须显式传 dry_run=False。
    未显式提供 partition_name 时会沿用参与增强配置中已启用的分区名称。
    返回键包含：scanned / deleted / unfollowed / skipped / skipped_unowned /
    skipped_whitelist / partition_name / max_days / delete_dynamic / dry_run。
    """
    # 防御：max_days 下限 1 天，避免 0/负数导致全量删除
    try:
        max_days = max(1, int(max_days))
    except (TypeError, ValueError):
        max_days = DEFAULT_MAX_DAYS
    partition_name = _resolve_partition_name(partition_name)
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
        "partition_name": partition_name,
        "max_days": max_days,
        "delete_dynamic": bool(delete_dynamic),
        "dry_run": bool(dry_run),
    }

    # 1) 删除超期转发动态（仅限 Binggo 归属台账内的动态）
    if delete_dynamic:
        exact_ids, legacy_source_ids = _owned_repost_dynamic_ids()
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
                # 归属校验（exact ownership）：
                # - 新记录：feed 转发自身 id ∈ exact_ids（Binggo 创建的精确匹配）
                # - 旧记录（无 created id）：源动态 id ∈ legacy_source_ids 兼容
                # 都不命中 → 非 Binggo 创建的转发绝不删除（含用户手动转发）
                owned_exact = dynamic_id in exact_ids
                owned_legacy = bool(source_id) and source_id in legacy_source_ids
                if not owned_exact and not owned_legacy:
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

    # 2) 分区批量取关。注意：这与“删除了哪些动态”是两个独立范围；
    # 只依据关注分区 + 白名单决定，不再用“对应 UP”这样的误导语义。
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
