"""参与增强配置（源自 LAS 的 is_copy_chat / at_users / needTopic / 乱序 / 随机延迟机制）。

配置文件：`config/participate_enhance.json`（可选，缺省全部关闭/保持现状）：

```json
{
  "copy_chat": {"enabled": true, "blockwords": ["抽奖", "互关"], "exclude_author": true},
  "at_users": [{"uid": 294887687, "name": "转发抽奖娘"}],
  "topic": "#每日抽奖#",
  "shuffle_targets": true,
  "action_interval_sec": {"min": 0.75, "max": 2.25}
}
```

- `copy_chat.enabled`：评论抄热评（随机评论区内容，剔除作者评论与屏蔽词）
- `at_users`：转发时 @ 的用户（含 ctrl 定位，真 @）
- `topic`：转发时追加的话题文本
- `shuffle_targets`：三连参与前乱序目标（防固定顺序被开奖机过滤）
- `action_interval_sec`：五连动作间隔随机范围（秒）

校验策略：保存前（Web API PUT）用 Pydantic 模型 `EnhanceSettingsModel` 强校验，
非法输入直接拒绝；读取（load / GET）保持宽容——磁盘旧配置中的非法字段
静默回退默认值，绝不抛错。
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from src.app_paths import config_dir

_lock = threading.RLock()
_cache: dict | None = None
_CACHE_MTIME: float | None = None

DEFAULTS: dict = {
    "copy_chat": {"enabled": False, "blockwords": [], "exclude_author": True},
    "at_users": [],
    "topic": "",
    "shuffle_targets": True,
    "action_interval_sec": {"min": 0.75, "max": 2.25},
    "partition": {"enabled": False, "name": "抽奖临时关注"},
}

# 校验上限（保守）
_MAX_AT_USERS = 50
_MAX_BLOCKWORDS = 200
_MAX_BLOCKWORD_LEN = 100
_MAX_TOPIC_LEN = 100
_MAX_NAME_LEN = 50
_MAX_INTERVAL_SEC = 600.0


def _require_str(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("必须是字符串")
    return value


def _require_bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError("必须是布尔值（true/false）")
    return value


class AtUserModel(BaseModel):
    """@ 用户：uid 为纯数字（接受数字/数字字符串，归一化为 int），name 为昵称。

    HTTP 写入路径：未知字段直接校验失败（拒绝 typo 静默吞掉）。
    """

    model_config = ConfigDict(extra="forbid")

    uid: int
    name: str = Field(default="", max_length=_MAX_NAME_LEN)

    @field_validator("uid", mode="before")
    @classmethod
    def _coerce_uid(cls, value: object) -> int:
        if isinstance(value, bool):
            raise ValueError("uid 必须是纯数字")
        if isinstance(value, int):
            if value <= 0:
                raise ValueError("uid 必须是大于 0 的纯数字")
            return value
        if isinstance(value, float) and value.is_integer() and value > 0:
            return int(value)
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
        raise ValueError("uid 必须是纯数字")

    @field_validator("name", mode="before")
    @classmethod
    def _coerce_name(cls, value: object) -> str:
        return _require_str(value)


class CopyChatModel(BaseModel):
    """抄热评：enabled 开关、blockwords 屏蔽词表、exclude_author 剔除作者。"""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    blockwords: list[str] = Field(default_factory=list)
    exclude_author: bool = True

    @field_validator("enabled", "exclude_author", mode="before")
    @classmethod
    def _coerce_bool(cls, value: object) -> bool:
        return _require_bool(value)

    @field_validator("blockwords", mode="before")
    @classmethod
    def _validate_blockwords(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            raise ValueError("必须是字符串列表")
        if len(value) > _MAX_BLOCKWORDS:
            raise ValueError(f"数量不能超过 {_MAX_BLOCKWORDS}（当前 {len(value)}）")
        for index, word in enumerate(value):
            if not isinstance(word, str):
                raise ValueError(f"第 {index} 条必须是字符串")
            if len(word) > _MAX_BLOCKWORD_LEN:
                raise ValueError(f"第 {index} 条长度不能超过 {_MAX_BLOCKWORD_LEN}（当前 {len(word)}）")
        return value


class ActionIntervalModel(BaseModel):
    """五连动作间隔随机范围（秒）：0 < min <= max，且 max <= 600。"""

    model_config = ConfigDict(extra="forbid")

    min: float = Field(default=0.75, gt=0)
    max: float = Field(default=2.25, gt=0)

    @model_validator(mode="after")
    def _check_range(self) -> "ActionIntervalModel":
        if self.min > self.max:
            raise ValueError(f"min（{self.min:g}）不能大于 max（{self.max:g}）")
        if self.max > _MAX_INTERVAL_SEC:
            raise ValueError(f"max 不能超过 {_MAX_INTERVAL_SEC:g} 秒（当前 {self.max:g}）")
        return self


class PartitionModel(BaseModel):
    """关注后自动移入的分区：enabled 开关、name 分区名。"""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    name: str = Field(default="抽奖临时关注", max_length=_MAX_NAME_LEN)

    @field_validator("enabled", mode="before")
    @classmethod
    def _coerce_enabled(cls, value: object) -> bool:
        return _require_bool(value)

    @field_validator("name", mode="before")
    @classmethod
    def _coerce_name(cls, value: object) -> str:
        return _require_str(value)


class EnhanceSettingsModel(BaseModel):
    """参与增强配置完整结构（字段与 DEFAULTS 一一对应，PUT 保存前强校验）。

    extra="forbid"：HTTP 写入路径上任何未知字段（如 shuffle_target 拼写错误）
    都直接校验失败，不再静默吞掉。磁盘容错加载由 sanitize_participate_enhance
    的逐字段 try 兜底，保持宽容。
    """

    model_config = ConfigDict(extra="forbid")

    copy_chat: CopyChatModel = Field(default_factory=CopyChatModel)
    at_users: list[AtUserModel] = Field(default_factory=list)
    topic: str = Field(default="", max_length=_MAX_TOPIC_LEN)
    shuffle_targets: bool = True
    action_interval_sec: ActionIntervalModel = Field(default_factory=ActionIntervalModel)
    partition: PartitionModel = Field(default_factory=PartitionModel)

    @field_validator("topic", mode="before")
    @classmethod
    def _coerce_topic(cls, value: object) -> str:
        return _require_str(value)

    @field_validator("shuffle_targets", mode="before")
    @classmethod
    def _coerce_shuffle(cls, value: object) -> bool:
        return _require_bool(value)

    @field_validator("at_users", mode="before")
    @classmethod
    def _check_at_users(cls, value: object) -> list[Any]:
        if not isinstance(value, list):
            raise ValueError("必须是用户列表")
        if len(value) > _MAX_AT_USERS:
            raise ValueError(f"数量不能超过 {_MAX_AT_USERS}（当前 {len(value)}）")
        return value

    @field_validator("at_users")
    @classmethod
    def _dedupe_at_users(cls, value: list[AtUserModel]) -> list[AtUserModel]:
        """按 uid 去重（保留首个出现的条目）。"""
        seen: set[int] = set()
        deduped: list[AtUserModel] = []
        for user in value:
            if user.uid in seen:
                continue
            seen.add(user.uid)
            deduped.append(user)
        return deduped


def _config_path() -> Path:
    return config_dir() / "participate_enhance.json"


def _deep_merge(defaults: dict, override: dict) -> dict:
    merged = dict(defaults)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def merge_participate_defaults(user_config: dict) -> dict:
    """把用户配置与默认值合并，返回结构完整的参与增强配置（供 Web API 用）。"""
    return _deep_merge(DEFAULTS, user_config)


def _format_loc(parts: Any) -> str:
    """把 Pydantic 错误 loc（如 ('at_users', 0, 'uid')）格式化为 at_users[0].uid。"""
    out = ""
    for part in parts:
        if part == "__root__":
            continue
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += f".{part}" if out else str(part)
    return out


def format_enhance_validation_error(exc: ValidationError) -> str:
    """把 Pydantic 校验错误转成可读信息（字段路径 + 原因），供 HTTP 400 返回。"""
    lines: list[str] = []
    for err in exc.errors():
        loc = _format_loc(err.get("loc") or ())
        msg = str(err.get("msg") or "").strip()
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, ") :].strip()
        elif msg == "Field required":
            msg = "缺少该字段"
        elif msg.startswith("Input should be a valid boolean"):
            msg = "必须是布尔值（true/false）"
        elif msg.startswith("Input should be a valid integer"):
            msg = "必须是整数"
        elif msg.startswith("Input should be a valid number"):
            msg = "必须是数字"
        elif msg.startswith("Input should be a valid string"):
            msg = "必须是字符串"
        elif msg.startswith("Input should be a valid list"):
            msg = "必须是列表"
        elif msg.startswith("Input should be a valid dictionary"):
            msg = "必须是 JSON 对象"
        elif msg.startswith("Extra inputs are not permitted"):
            msg = "未知字段"
        elif msg.startswith("String should have at most"):
            msg = "长度超出限制"
        elif msg.startswith("Input should be greater than"):
            msg = "必须大于 0"
        lines.append(f"{loc}: {msg}" if loc else msg)
    return "；".join(lines[:8])


def sanitize_participate_enhance(raw: dict | None) -> dict:
    """宽容加载：磁盘旧配置中的非法字段静默回退默认值，绝不抛错。

    先整体校验；失败则按顶层字段逐个容错（合法字段保留、非法字段回退默认），
    返回结构完整的配置（含全部默认字段）。
    """
    if not isinstance(raw, dict):
        return _deep_merge(DEFAULTS, {})
    try:
        return EnhanceSettingsModel.model_validate(raw).model_dump()
    except ValidationError:
        cleaned: dict[str, Any] = {}
        for key in EnhanceSettingsModel.model_fields:
            if key not in raw:
                continue
            try:
                cleaned[key] = EnhanceSettingsModel.model_validate({key: raw[key]}).model_dump()[key]
            except ValidationError:
                continue  # 该字段非法，保留默认
        return _deep_merge(DEFAULTS, cleaned)


def load_participate_enhance() -> dict:
    """加载参与增强配置（缺省=现状）。文件变化时自动重载。"""
    global _cache, _CACHE_MTIME
    path = _config_path()
    with _lock:
        mtime = path.stat().st_mtime if path.exists() else None
        if _cache is not None and mtime == _CACHE_MTIME:
            return _cache
        raw: dict = {}
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                raw = {}
        if not isinstance(raw, dict):
            raw = {}
        _cache = sanitize_participate_enhance(raw)
        _CACHE_MTIME = mtime
        return _cache


def reset_participate_enhance_cache() -> None:
    """测试用：清空缓存强制重载。"""
    global _cache, _CACHE_MTIME
    with _lock:
        _cache = None
        _CACHE_MTIME = None
