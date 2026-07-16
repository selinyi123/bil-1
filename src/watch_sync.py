from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from typing import Callable

from src.bilibili_client import BilibiliClient
from src.sources.common import is_valid_dynamic_id, normalize_activity_id, opus_link
from src.state_store import DATA_DIR, get_watch_last_synced_at
from src.watch_feed import collect_forward_links_for_user
from src.watch_users import WatchUser, list_watch_users

WATCH_SOURCE_ID = "WATCH"
OUTPUT_PATH = DATA_DIR / "output" / "watch_latest.json"
MAX_WINDOW_SECONDS = 10 * 24 * 3600
FIRST_SYNC_WINDOW_SECONDS = 10 * 24 * 3600
USER_REQUEST_DELAY = 0.45

ProgressCallback = Callable[[int, int, str], None]


@dataclass
class WatchUserScanResult:
    mid: int
    name: str
    ok: bool
    link_count: int
    forward_count: int
    message: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class WatchSyncResult:
    source_id: str
    synced_at: int
    window_start: int
    window_end: int
    activity_links: list[str]
    users_total: int
    users_ok: int
    users_failed: list[dict]
    user_results: list[dict]
    link_count: int

    def to_dict(self) -> dict:
        return asdict(self)


def compute_sync_window(*, now: int | None = None, last_synced_at: int | None = None) -> tuple[int, int]:
    current = int(now if now is not None else time.time())
    if last_synced_at is None or last_synced_at <= 0:
        return current - FIRST_SYNC_WINDOW_SECONDS, current
    earliest = current - MAX_WINDOW_SECONDS
    since = max(int(last_synced_at), earliest)
    return since, current


def _dedupe_activity_links(raw_links: list[str]) -> list[str]:
    """合并多用户扫描结果时按动态 ID 去重，仅整理采集列表。"""
    ordered: list[str] = []
    seen: set[str] = set()
    for raw_url in raw_links:
        dynamic_id = normalize_activity_id(str(raw_url))
        if not dynamic_id or dynamic_id in seen:
            continue
        seen.add(dynamic_id)
        ordered.append(opus_link(dynamic_id))
    return ordered


def sync_watch_forwards(
    *,
    users: list[WatchUser] | None = None,
    on_progress: ProgressCallback | None = None,
) -> WatchSyncResult:
    """拉取监控用户在时间窗口内的转发原动态链接（仅采集，不做活动库去重）。"""
    sync_started_at = int(time.time())
    last_synced_at = get_watch_last_synced_at()
    window_start, window_end = compute_sync_window(now=sync_started_at, last_synced_at=last_synced_at)

    watch_users = users if users is not None else list_watch_users()
    total = len(watch_users)
    if total == 0:
        raise RuntimeError("监控用户列表为空，请先在设置中添加用户")

    window_links: list[str] = []
    user_results: list[WatchUserScanResult] = []

    with BilibiliClient(timeout=30.0) as client:
        for index, user in enumerate(watch_users, start=1):
            if on_progress:
                on_progress(index, total, f"正在扫描 {user.name} 的转发动态…")
            try:
                forwards = collect_forward_links_for_user(
                    client,
                    user.mid,
                    since_ts=window_start,
                    until_ts=window_end,
                )
                links = [item.url for item in forwards if is_valid_dynamic_id(item.dynamic_id)]
                user_results.append(
                    WatchUserScanResult(
                        mid=user.mid,
                        name=user.name,
                        ok=True,
                        link_count=len(links),
                        forward_count=len(forwards),
                        message=f"转发 {len(forwards)} 条，链接 {len(links)} 条",
                    )
                )
                window_links.extend(links)
            except Exception as exc:
                message = str(exc).strip() or "扫描失败"
                raise RuntimeError(f"扫描用户 {user.name}（{user.mid}）失败：{message}") from exc
            if index < total:
                time.sleep(USER_REQUEST_DELAY)

    activity_links = _dedupe_activity_links(window_links)

    return WatchSyncResult(
        source_id=WATCH_SOURCE_ID,
        synced_at=sync_started_at,
        window_start=window_start,
        window_end=window_end,
        activity_links=activity_links,
        users_total=total,
        users_ok=total,
        users_failed=[],
        user_results=[item.to_dict() for item in user_results],
        link_count=len(activity_links),
    )


def save_watch_result(result: WatchSyncResult) -> WatchSyncResult:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source_id": result.source_id,
        "synced_at": result.synced_at,
        "window_start": result.window_start,
        "window_end": result.window_end,
        "checked_at": result.synced_at,
        "activity_links": result.activity_links,
        "link_count": result.link_count,
        "users_total": result.users_total,
        "users_ok": result.users_ok,
        "users_failed": result.users_failed,
        "user_results": result.user_results,
    }
    tmp_path = OUTPUT_PATH.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(OUTPUT_PATH)
    return result
