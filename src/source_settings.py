"""DS-8/9/10 的受控配置读写服务。

Web 控制面只暴露业务字段，不暴露任意文件路径写入：
- DS-8: dynamic_ids（ID/动态链接输入，落盘为规范 ID）
- DS-9: tags（话题名）
- DS-10: 以 entry id 增删外部源；读取时 URL 凭据/查询值脱敏

DS-10 兼容已有 file:// 源，但 Web 新增 file:// 时仅允许位于 BINGGO_HOME
之下，避免把“数据源配置”退化成浏览器任意本地文件读取能力。直接编辑
config/api_sources.txt 仍保留旧版高级兼容语义。
"""
from __future__ import annotations

import hashlib
import threading
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from src.app_paths import config_dir, user_home
from src.secure_files import write_text_secret
from src.sources.common import normalize_dynamic_id

_DS8_FILE = "manual_dyids.txt"
_DS9_FILE = "topic_tags.txt"
_DS10_FILE = "api_sources.txt"
_MAX_DS8_IDS = 1000
_MAX_DS9_TAGS = 200
_MAX_DS10_SOURCES = 100
_MAX_SOURCE_LENGTH = 4096
_lock = threading.RLock()


def _path(name: str) -> Path:
    return config_dir() / name


def _read_lines(name: str) -> list[str]:
    path = _path(name)
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    result: list[str] = []
    seen: set[str] = set()
    for raw in lines:
        value = raw.strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _write_lines(name: str, values: list[str], *, secret: bool = False) -> None:
    text = "\n".join(values)
    if text:
        text += "\n"
    path = _path(name)
    # DS-10 URL 常含 token；统一原子写。其余文件也复用同一安全写路径，
    # secret 参数只保留语义标记，权限收紧对三者均无害。
    write_text_secret(path, text)


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def get_ds8_dynamic_ids() -> list[str]:
    """读取 DS-8，并把历史链接格式规范化为动态 ID 返回。"""
    result: list[str] = []
    for raw in _read_lines(_DS8_FILE):
        dynamic_id = normalize_dynamic_id(raw)
        if dynamic_id:
            result.append(dynamic_id)
    return _dedupe(result)


def set_ds8_dynamic_ids(values: list[str]) -> list[str]:
    if len(values) > _MAX_DS8_IDS:
        raise ValueError(f"DS-8 最多允许 {_MAX_DS8_IDS} 个动态")
    normalized: list[str] = []
    for index, raw in enumerate(values, start=1):
        value = str(raw or "").strip()
        if not value:
            continue
        dynamic_id = normalize_dynamic_id(value)
        if not dynamic_id:
            raise ValueError(f"DS-8 第 {index} 项不是有效的 B 站动态 ID/链接")
        normalized.append(dynamic_id)
    normalized = _dedupe(normalized)
    with _lock:
        _write_lines(_DS8_FILE, normalized)
    return normalized


def get_ds9_tags() -> list[str]:
    return _read_lines(_DS9_FILE)


def set_ds9_tags(values: list[str]) -> list[str]:
    if len(values) > _MAX_DS9_TAGS:
        raise ValueError(f"DS-9 最多允许 {_MAX_DS9_TAGS} 个话题")
    tags: list[str] = []
    for index, raw in enumerate(values, start=1):
        tag = str(raw or "").strip().lstrip("#").rstrip("#").strip()
        if not tag:
            continue
        if len(tag) > 80:
            raise ValueError(f"DS-9 第 {index} 个话题过长（最多 80 字）")
        if any(ch in tag for ch in ("\r", "\n", "\x00")):
            raise ValueError(f"DS-9 第 {index} 个话题包含非法字符")
        tags.append(tag)
    tags = _dedupe(tags)
    with _lock:
        _write_lines(_DS9_FILE, tags)
    return tags


def external_source_id(source: str) -> str:
    return hashlib.sha256(str(source).encode("utf-8")).hexdigest()


def _file_source_path(source: str) -> Path:
    parsed = urlsplit(source)
    netloc = parsed.netloc
    raw_path = parsed.path
    if len(netloc) == 2 and netloc[1] == ":":
        raw_path = netloc + raw_path
    elif len(raw_path) >= 3 and raw_path[0] == "/" and raw_path[2] == ":":
        raw_path = raw_path[1:]
    return Path(raw_path).expanduser()


def validate_external_source(source: str, *, web_safe_file: bool = True) -> str:
    value = str(source or "").strip()
    if not value:
        raise ValueError("外部源不能为空")
    if len(value) > _MAX_SOURCE_LENGTH:
        raise ValueError(f"外部源 URL 过长（最多 {_MAX_SOURCE_LENGTH} 字符）")
    parsed = urlsplit(value)
    scheme = parsed.scheme.lower()
    if scheme in {"http", "https"}:
        if not parsed.hostname:
            raise ValueError("HTTP(S) 外部源缺少主机名")
        return value
    if scheme == "file":
        path = _file_source_path(value)
        if not str(path):
            raise ValueError("file:// 外部源缺少路径")
        if web_safe_file:
            try:
                resolved = path.resolve(strict=False)
                home = user_home().resolve(strict=False)
                resolved.relative_to(home)
            except (OSError, ValueError):
                raise ValueError("Web 仅允许添加 BINGGO_HOME 目录内的 file:// 数据源")
        return value
    raise ValueError("DS-10 仅支持 http://、https:// 或 file:// 数据源")


def _mask_http_source(source: str) -> str:
    parsed = urlsplit(source)
    host = parsed.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = f":{parsed.port}" if parsed.port else ""
    userinfo = "***@" if parsed.username is not None or parsed.password is not None else ""
    netloc = f"{userinfo}{host}{port}"
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    query = urlencode([(key, "***") for key, _value in query_pairs])
    return urlunsplit((parsed.scheme, netloc, parsed.path, query, ""))


def mask_external_source(source: str) -> str:
    parsed = urlsplit(source)
    if parsed.scheme.lower() in {"http", "https"}:
        try:
            return _mask_http_source(source)
        except ValueError:
            return f"{parsed.scheme}://{parsed.hostname or '***'}/…"
    if parsed.scheme.lower() == "file":
        path = _file_source_path(source)
        name = path.name or "local.json"
        return f"file://…/{name}"
    return "***"


def get_ds10_sources() -> list[str]:
    return _read_lines(_DS10_FILE)


def list_ds10_entries() -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for source in get_ds10_sources():
        parsed = urlsplit(source)
        entries.append(
            {
                "id": external_source_id(source),
                "kind": parsed.scheme.lower() or "unknown",
                "display": mask_external_source(source),
            }
        )
    return entries


def add_ds10_source(source: str) -> dict[str, str]:
    value = validate_external_source(source, web_safe_file=True)
    with _lock:
        sources = get_ds10_sources()
        if value not in sources:
            if len(sources) >= _MAX_DS10_SOURCES:
                raise ValueError(f"DS-10 最多允许 {_MAX_DS10_SOURCES} 个外部源")
            sources.append(value)
            _write_lines(_DS10_FILE, sources, secret=True)
    return {
        "id": external_source_id(value),
        "kind": urlsplit(value).scheme.lower(),
        "display": mask_external_source(value),
    }


def remove_ds10_source(source_id: str) -> bool:
    target = str(source_id or "").strip().lower()
    if len(target) != 64 or any(ch not in "0123456789abcdef" for ch in target):
        return False
    with _lock:
        sources = get_ds10_sources()
        kept = [source for source in sources if external_source_id(source) != target]
        if len(kept) == len(sources):
            return False
        _write_lines(_DS10_FILE, kept, secret=True)
        return True


def get_source_settings_payload() -> dict:
    ds8 = get_ds8_dynamic_ids()
    ds9 = get_ds9_tags()
    ds10 = list_ds10_entries()
    return {
        "ds8": {"dynamic_ids": ds8, "count": len(ds8)},
        "ds9": {"tags": ds9, "count": len(ds9)},
        "ds10": {
            "entries": ds10,
            "count": len(ds10),
            "file_scope": str(user_home()),
        },
    }
