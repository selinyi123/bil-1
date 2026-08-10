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
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

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
        _cache = _deep_merge(DEFAULTS, raw)
        _CACHE_MTIME = mtime
        return _cache


def reset_participate_enhance_cache() -> None:
    """测试用：清空缓存强制重载。"""
    global _cache, _CACHE_MTIME
    with _lock:
        _cache = None
        _CACHE_MTIME = None
