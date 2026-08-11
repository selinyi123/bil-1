"""DS-10 外部 API 源（P1-4，源自 LAS 的 APIs 源）。

读取 `config/api_sources.txt`（每行一个 URL 或 `file://` 本地 JSON 路径），
拉取外部抽奖信息 JSON 并提取动态 ID 交给发现流水线。

兼容的 JSON 结构（任选其一）：
- `{"lottery_info": [{"dyid": "..."}], ...}`（LAS 存档格式）
- `{"dynamic_ids": ["..."]}`
- `{"links": ["https://www.bilibili.com/opus/..."]}`
- 纯数组 `["<dyid 或链接>", ...]`

增量语义（P2 #11）：按源分别保存 fingerprint（复用 `SourceCheckpointRow.cv_id`
列存 JSON dict {sha256(source): {fp, etag, lm, mtime}}，key 为完整源 URL 的
sha256 摘要，绝不落明文 URL/凭据）。HTTP 源优先用 ETag / Last-Modified
条件请求（304 → 未变化）；无条件头支持时回退到内容 sha256。file:// 源用内容
sha256（主判据）+ mtime（记录）。全部源均未变化 → updated=False 且不触发流水线；
任一源变化 → updated=True，activity_links 只含变化源的链接（未变化源的链接
已在库/已处理，无需重复提交）。
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from src.app_paths import config_dir
from src.sources.common import (
    CheckResult,
    load_source_fingerprint,
    normalize_dynamic_id,
    opus_link,
    save_result as write_result,
)
from src.state_store import DATA_DIR

SOURCE_ID = "DS-10"
OUTPUT_PATH = DATA_DIR / "output" / "ds10_latest.json"
CONFIG_FILE = config_dir() / "api_sources.txt"
CONTAINER_PLACEHOLDER = "api://sources"

_HEX_DIGITS = frozenset("0123456789abcdef")


def _source_key(source: str) -> str:
    """源指纹映射的稳定 key：完整 URL 的 sha256 摘要。

    完整 URL 可能携带 ?token= 等凭据，绝不能以明文落库（cv_id 列），
    因此用哈希作为 map 的 key。
    """
    return hashlib.sha256(str(source).encode("utf-8")).hexdigest()


def _looks_like_hash_key(key: str) -> bool:
    """判断 key 是否已是 sha256（64 位小写 hex）形式的指纹 key。"""
    return len(key) == 64 and all(c in _HEX_DIGITS for c in key)


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


def _payload_fingerprint(payload: object) -> str:
    """载荷内容指纹：规范化 JSON 文本的 sha256（键排序，稳定跨轮次）。"""
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _fetch_payload_with_meta(
    source: str, prev_meta: dict | None
) -> tuple[object | None, dict[str, str]]:
    """拉取单个外部源，返回 (payload, meta)。

    - payload 为 None 表示 HTTP 304（条件请求命中，内容未变化）；
    - meta 记录用于下次条件请求的 ETag / Last-Modified（HTTP）或 mtime（file://）；
    - 失败抛 RuntimeError。
    """
    prev_meta = prev_meta or {}
    if source.startswith("file://"):
        # 兼容 file:///C:/path、file://C:/path 与 file:///abs/path 三种写法
        from urllib.parse import urlparse

        parsed = urlparse(source)
        netloc = parsed.netloc
        raw_path = parsed.path
        if len(netloc) == 2 and netloc[1] == ":":
            # Windows: "file://C:/..." 的盘符被解析进 netloc → C:/...
            raw_path = netloc + raw_path
        elif len(raw_path) >= 3 and raw_path[0] == "/" and raw_path[2] == ":":
            # Windows: "file:///C:/..." → C:/...
            raw_path = raw_path[1:]
        path = Path(raw_path)
        if not path.exists():
            raise RuntimeError(f"外部源文件不存在: {path}")
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            mtime = str(int(path.stat().st_mtime))
        except OSError as exc:
            raise RuntimeError(f"外部源读取失败: {source}: {exc}") from exc
        try:
            payload = json.loads(text)
        except (ValueError, TypeError) as exc:
            raise RuntimeError(f"外部源 JSON 解析失败: {source}") from exc
        return payload, {"mtime": mtime}

    import httpx

    from src.proxy_config import get_proxy_url

    proxy = get_proxy_url()
    headers: dict[str, str] = {}
    etag = prev_meta.get("etag") or ""
    last_modified = prev_meta.get("lm") or ""
    if etag:
        headers["If-None-Match"] = etag
    elif last_modified:
        headers["If-Modified-Since"] = last_modified
    try:
        response = httpx.get(
            source,
            timeout=20.0,
            follow_redirects=True,
            proxy=proxy,
            headers=headers,
        )
    except (httpx.HTTPError, OSError) as exc:
        # ConnectError / TimeoutException 等 transport 异常统一包装为
        # RuntimeError：外层 check_update 只捕获 RuntimeError 做单源降级，
        # 避免某个源断连中断整个 DS-10。
        raise RuntimeError(f"外部源请求失败: {source}: {exc}") from exc
    if response.status_code == 304:
        # 条件请求命中：内容与上次相同
        return None, {}
    if response.status_code != 200:
        raise RuntimeError(f"外部源 HTTP {response.status_code}: {source}")
    try:
        payload = json.loads(response.text)
    except (ValueError, TypeError) as exc:
        raise RuntimeError(f"外部源 JSON 解析失败: {source}") from exc
    meta: dict[str, str] = {}
    new_etag = response.headers.get("ETag") or ""
    new_lm = response.headers.get("Last-Modified") or ""
    if new_etag:
        meta["etag"] = new_etag
    if new_lm:
        meta["lm"] = new_lm
    return payload, meta


def _load_prev_fp_map() -> dict[str, dict[str, str]]:
    """解析上次提交的按源 fingerprint 映射（cv_id 列 JSON）。

    旧版本曾以完整 URL（可能含 ?token= 凭据）为 key 写入；加载时统一
    换算为 sha256 指纹 key，此后读写均不再出现明文 URL。
    """
    raw = load_source_fingerprint(SOURCE_ID)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    result: dict[str, dict[str, str]] = {}
    for key, value in parsed.items():
        if not isinstance(value, dict):
            continue
        raw_key = str(key)
        norm_key = raw_key if _looks_like_hash_key(raw_key) else _source_key(raw_key)
        result[norm_key] = value
    return result


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
    now = int(time.time())

    prev_map = _load_prev_fp_map()
    # 只保留当前 sources 对应的 key：配置里已移除的源（或指纹格式变化）
    # 不得残留旧 fingerprint，避免 map 无限增长。
    current_keys = {_source_key(source) for source in sources}
    new_map: dict[str, dict[str, str]] = {
        key: dict(value) for key, value in prev_map.items() if key in current_keys
    }
    # 以旧映射为基底：部分源失败时保留其旧 fingerprint/条件请求头（否则
    # commit 会丢掉失败源的 meta，下次被迫全量拉取并重复触发流水线）
    links: list[str] = []
    errors: list[str] = []
    changed = False
    for source in sources:
        key = _source_key(source)
        try:
            # force 时不带上次条件头：必须拿到 200 全量内容，强制按"有变化"处理
            prev_meta = None if force else prev_map.get(key)
            payload, meta = _fetch_payload_with_meta(source, prev_meta)
        except RuntimeError as exc:
            errors.append(str(exc))
            continue
        if payload is None:
            # HTTP 304：内容未变化，保留上次指纹与条件请求头
            new_map[key] = dict(prev_map.get(key) or {})
            continue
        fp = _payload_fingerprint(payload)
        entry: dict[str, str] = {"fp": fp}
        entry.update(meta)
        new_map[key] = entry
        prev_entry = prev_map.get(key) or {}
        # 变化判定：内容指纹变化，或条件请求头（etag/lm）轮换。
        # mtime 不参与判定（file:// 源每次读取都会变，仅作记录）。
        # 链接只在内容真正变化时收集；etag 轮换仅推进指纹避免重复全量拉取。
        fp_changed = fp != prev_entry.get("fp")
        if force or fp_changed or entry.get("etag") != prev_entry.get("etag") or entry.get("lm") != prev_entry.get("lm"):
            changed = True
        if fp_changed:
            for did in _extract_dynamic_ids(payload):
                links.append(opus_link(did))

    if sources and errors and len(errors) == len(sources):
        # 全部源失败：显式抛错（由调用方计入失败），绝不静默伪装成"无更新"
        raise RuntimeError("DS-10 全部外部源失败: " + "; ".join(errors))

    if not links and not changed:
        # 无新动态且内容/条件头均无变化：不触发流水线
        return CheckResult(
            source_id=SOURCE_ID,
            updated=False,
            container_url=CONTAINER_PLACEHOLDER,
            container_id="",
            title="外部 API 源（无动态）",
            published_at=0,
            previous_container_url=CONTAINER_PLACEHOLDER,
            activity_links=[],
            checked_at=now,
        )
    if not links:
        # 内容/条件头有变化但提取不到新动态（空批次）：
        # updated=True 推进指纹（cv_id 随 commit 落库），避免下轮重复全量拉取；
        # 空 activity_links 使调用方流水线自然跳过。
        return CheckResult(
            source_id=SOURCE_ID,
            updated=True,
            container_url=CONTAINER_PLACEHOLDER,
            container_id="api",
            title=f"外部 API 源（{len(sources)} 个来源，0 条动态）",
            published_at=now,
            previous_container_url=CONTAINER_PLACEHOLDER,
            activity_links=[],
            checked_at=now,
            cv_id=json.dumps(new_map, sort_keys=True, ensure_ascii=False, separators=(",", ":")),
        )
    return CheckResult(
        source_id=SOURCE_ID,
        updated=True,
        container_url=CONTAINER_PLACEHOLDER,
        container_id="api",
        title=f"外部 API 源（{len(sources)} 个来源，{len(links)} 条动态）",
        published_at=now,
        previous_container_url=CONTAINER_PLACEHOLDER,
        activity_links=links,
        checked_at=now,
        # 复用 cv_id 承载按源 fingerprint JSON，由 commit_source_checkpoint 持久化
        cv_id=json.dumps(new_map, sort_keys=True, ensure_ascii=False, separators=(",", ":")),
    )


def save_result(result: CheckResult) -> Path | None:
    return write_result(OUTPUT_PATH, result)
