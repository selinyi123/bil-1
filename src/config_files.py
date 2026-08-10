"""config 目录下 JSON 配置文件的通用读写（供设置页编辑 participate_enhance/notify 等）。

写前校验必须是 dict，用原子写盘避免半写文件。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.app_paths import config_dir

ALLOWED_NAMES = frozenset({"participate_enhance.json", "notify.json"})

# 配置中的凭据字段（GET 回显脱敏、PUT 恢复），避免密钥经前端 textarea 明文外泄
SENSITIVE_FIELDS = frozenset(
    {
        "sendkey",
        "sckey",
        "key",
        "token",
        "pushkey",
        "appkey",
        "secret",
        "corpsecret",
        "password",
        "webhook",
        "access_token",
    }
)
_SECRET_PLACEHOLDER = "****"


def config_json_path(name: str) -> Path:
    if name not in ALLOWED_NAMES:
        raise ValueError(f"不允许的配置文件: {name}")
    return config_dir() / name


def load_config_json(name: str) -> dict[str, Any]:
    """读取配置文件；不存在返回空 dict，损坏返回空 dict。"""
    path = config_json_path(name)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def save_config_json(name: str, data: dict[str, Any]) -> None:
    """原子写配置文件（仅接受 dict，含默认值合并后的完整结构）。"""
    if not isinstance(data, dict):
        raise ValueError("配置内容必须是 JSON 对象")
    path = config_json_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp_path.replace(path)


def sanitize_config_secrets(data: dict[str, Any]) -> dict[str, Any]:
    """递归把配置中的凭据字段值替换为占位符（用于 GET 回显）。"""
    return _sanitize_value(data)  # type: ignore[return-value]


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                _SECRET_PLACEHOLDER
                if key in SENSITIVE_FIELDS and item not in ("", None)
                else _sanitize_value(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    return value


def restore_config_secrets(saved: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """PUT 保存前递归恢复：incoming 中为占位符的字段沿用已保存的真实值。

    用户要清空凭据时直接留空字符串即可（空串不会被当成占位符）。
    """
    return _restore_value(saved, incoming)  # type: ignore[return-value]


def _restore_value(saved: Any, incoming: Any) -> Any:
    if isinstance(incoming, dict):
        return {
            key: (
                (saved or {}).get(key)
                if key in SENSITIVE_FIELDS
                and value == _SECRET_PLACEHOLDER
                and isinstance((saved or {}).get(key), str)
                else _restore_value((saved or {}).get(key), value)
            )
            for key, value in incoming.items()
        }
    if isinstance(incoming, list):
        return [_restore_value(saved, item) for item in incoming]
    return incoming
