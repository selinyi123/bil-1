"""DS-10 外部 API 源（P1-4，源自 LAS 的 APIs 源）。

读取 `config/api_sources.txt`（每行一个 URL 或 `file://` 本地 JSON 路径），
拉取外部抽奖信息 JSON 并提取动态 ID 交给发现流水线。

兼容的 JSON 结构（任选其一）：
- `{"lottery_info": [{"dyid": "..."}], ...}`（LAS 存档格式）
- `{"dynamic_ids": ["..."]}`
- `{"links": ["https://www.bilibili.com/opus/..."]}`
- 纯数组 `["<dyid 或链接>", ...]`
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from src.app_paths import config_dir
from src.sources.common import (
    CheckResult,
    load_previous_output,
    normalize_dynamic_id,
    opus_link,
    save_result as write_result,
)
from src.state_store import DATA_DIR

SOURCE_ID = "DS-10"
OUTPUT_PATH = DATA_DIR / "output" / "ds10_latest.json"
CONFIG_FILE = config_dir() / "api_sources.txt"
CONTAINER_PLACEHOLDER = "api://sources"


def _read_sources() -> list[str]:
    """读取外部源配置（每行一个 URL 或 file:// 路径）。"""
    if not CONFIG_FILE.exists():
        return []
    sources: list[str] = []
    seen: set[str] = set()
    for line in CONFIG_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        source = line.strip()
        if source and source not in seen:
            seen.add(source)
            sources.append(source)
    return sources


def _fetch_payload(source: str) -> object:
    """拉取单个外部源，返回 JSON 对象（dict/list）；失败抛 RuntimeError。"""
    if source.startswith("file://"):
        # 兼容 file:///C:/path 与 file://C:/path 两种写法
        from urllib.parse import urlparse

        parsed = urlparse(source)
        raw_path = parsed.path
        if len(raw_path) >= 3 and raw_path[0] == "/" and raw_path[2] == ":":
            raw_path = raw_path[1:]  # /C:/... → C:/...
        path = Path(raw_path)
        if not path.exists():
            raise RuntimeError(f"外部源文件不存在: {path}")
        text = path.read_text(encoding="utf-8", errors="replace")
    else:
        import httpx

        from src.proxy_config import get_proxy_url

        proxy = get_proxy_url()
        response = httpx.get(source, timeout=20.0, follow_redirects=True, proxy=proxy)
        if response.status_code != 200:
            raise RuntimeError(f"外部源 HTTP {response.status_code}: {source}")
        text = response.text
    try:
        return json.loads(text)
    except (ValueError, TypeError) as exc:
        raise RuntimeError(f"外部源 JSON 解析失败: {source}") from exc


def _extract_dynamic_ids(payload: object) -> list[str]:
    """从外部源载荷中宽松提取动态 ID。"""
    raw: list[str] = []
    if isinstance(payload, list):
        raw.extend(payload)
    elif isinstance(payload, dict):
        lottery_info = payload.get("lottery_info")
        if isinstance(lottery_info, list):
            for item in lottery_info:
                if isinstance(item, dict):
                    dyid = item.get("dyid") or item.get("dynamic_id")
                    if dyid:
                        raw.append(str(dyid))
        for key in ("dynamic_ids", "links"):
            value = payload.get(key)
            if isinstance(value, list):
                raw.extend(value)
    ids: list[str] = []
    seen: set[str] = set()
    for token in raw:
        dynamic_id = normalize_dynamic_id(str(token))
        if not dynamic_id or dynamic_id in seen:
            continue
        seen.add(dynamic_id)
        ids.append(dynamic_id)
    return ids


def check_update(*, force: bool = False) -> CheckResult:
    sources = _read_sources()
    links: list[str] = []
    errors: list[str] = []
    for source in sources:
        try:
            payload = _fetch_payload(source)
        except RuntimeError as exc:
            errors.append(str(exc))
            continue
        for did in _extract_dynamic_ids(payload):
            links.append(opus_link(did))

    if not links:
        prev_output = load_previous_output(OUTPUT_PATH)
        return CheckResult(
            source_id=SOURCE_ID,
            updated=False,
            container_url=CONTAINER_PLACEHOLDER,
            container_id="",
            title="外部 API 源（无动态）",
            published_at=0,
            previous_container_url=CONTAINER_PLACEHOLDER,
            activity_links=(prev_output or {}).get("activity_links") or [],
            checked_at=int(time.time()),
        )
    return CheckResult(
        source_id=SOURCE_ID,
        updated=True,
        container_url=CONTAINER_PLACEHOLDER,
        container_id="api",
        title=f"外部 API 源（{len(sources)} 个来源，{len(links)} 条动态）",
        published_at=int(time.time()),
        previous_container_url=CONTAINER_PLACEHOLDER,
        activity_links=links,
        checked_at=int(time.time()),
    )


def save_result(result: CheckResult) -> Path | None:
    return write_result(OUTPUT_PATH, result)
