"""config_files 配置读写测试。"""
from __future__ import annotations

import pytest

from src.config_files import (
    ALLOWED_NAMES,
    config_json_path,
    load_config_json,
    save_config_json,
)


def test_save_and_load_roundtrip(isolated_home) -> None:
    data = {"topic": "#抽奖#", "copy_chat": {"enabled": True}}
    save_config_json("participate_enhance.json", data)
    assert load_config_json("participate_enhance.json") == data
    assert config_json_path("participate_enhance.json").exists()


def test_load_missing_returns_empty(isolated_home) -> None:
    assert load_config_json("notify.json") == {}


def test_load_corrupt_returns_empty(isolated_home) -> None:
    path = config_json_path("notify.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not valid json", encoding="utf-8")
    assert load_config_json("notify.json") == {}


def test_save_rejects_non_dict(isolated_home) -> None:
    with pytest.raises(ValueError):
        save_config_json("notify.json", ["list"])  # type: ignore[arg-type]


def test_disallowed_name_rejected() -> None:
    with pytest.raises(ValueError):
        config_json_path("secret.txt")
    assert "notify.json" in ALLOWED_NAMES


def test_sanitize_and_restore_secrets(isolated_home) -> None:
    from src.config_files import restore_config_secrets, sanitize_config_secrets

    saved = {"channels": {"sct": {"sendkey": "REAL-KEY"}, "bark": {"key": "BK"}}, "keywords": ["中奖"]}
    save_config_json("notify.json", saved)

    sanitized = sanitize_config_secrets(load_config_json("notify.json"))
    assert sanitized["channels"]["sct"]["sendkey"] == "****"
    assert sanitized["channels"]["bark"]["key"] == "****"
    assert sanitized["keywords"] == ["中奖"]  # 非敏感字段原样

    # PUT 回来：占位符恢复真实值，空字符串表示清除（不恢复）
    restored = restore_config_secrets(saved, {"channels": {"sct": {"sendkey": "****"}, "bark": {"key": ""}}})
    assert restored["channels"]["sct"]["sendkey"] == "REAL-KEY"
    assert restored["channels"]["bark"]["key"] == ""

    # 顶层敏感键同样处理
    assert sanitize_config_secrets({"secret": "x"}) == {"secret": "****"}
    assert restore_config_secrets({"secret": "y"}, {"secret": "****"}) == {"secret": "y"}


def test_sanitize_covers_notify_channel_secrets(isolated_home) -> None:
    """notify.json 全部渠道的真实敏感键名必须被脱敏/恢复（含非通用命名）。"""
    from src.config_files import restore_config_secrets, sanitize_config_secrets

    saved = {
        "channels": {
            "telegram": {"bot_token": "TG-REAL", "chat_id": "123"},
            "email": {"user": "me@x.com", "pass": "SMTP-REAL", "host": "smtp.x.com"},
            "bark": {"push": "BARK-KEY", "sound": "alarm"},
            "serverchan": {"sckey": "SC-REAL"},
            "sct": {"sendkey": "SCT-REAL"},
            "dingtalk": {"token": "DT-REAL", "secret": "DT-SEC"},
        }
    }
    sanitized = sanitize_config_secrets(saved)
    assert sanitized["channels"]["telegram"]["bot_token"] == "****"
    assert sanitized["channels"]["email"]["pass"] == "****"
    assert sanitized["channels"]["bark"]["push"] == "****"
    # 非敏感字段保持原样
    assert sanitized["channels"]["telegram"]["chat_id"] == "123"
    assert sanitized["channels"]["email"]["user"] == "me@x.com"

    incoming = {
        "channels": {
            "telegram": {"bot_token": "****", "chat_id": "456"},
            "email": {"pass": "****", "user": "me@x.com"},
            "bark": {"push": ""},
        }
    }
    restored = restore_config_secrets(saved, incoming)
    assert restored["channels"]["telegram"]["bot_token"] == "TG-REAL"
    assert restored["channels"]["email"]["pass"] == "SMTP-REAL"
    # 空字符串表示清除，不恢复
    assert restored["channels"]["bark"]["push"] == ""


def test_restore_secrets_in_list_uses_same_index(isolated_home) -> None:
    """列表内的占位符必须按同索引恢复，不能拿整个 saved 列表去比对。"""
    from src.config_files import restore_config_secrets

    saved = {
        "channels": [
            {"name": "a", "token": "TOKEN-A"},
            {"name": "b", "token": "TOKEN-B"},
        ]
    }
    incoming = {
        "channels": [
            {"name": "a", "token": "****"},
            {"name": "b", "token": "****"},
        ]
    }
    restored = restore_config_secrets(saved, incoming)
    assert restored["channels"][0]["token"] == "TOKEN-A"
    assert restored["channels"][1]["token"] == "TOKEN-B"

    # incoming 比 saved 长时，多出来的项没有旧值可恢复，占位符原样保留
    longer = {"channels": incoming["channels"] + [{"name": "c", "token": "****"}]}
    restored_longer = restore_config_secrets(saved, longer)
    assert restored_longer["channels"][2]["token"] == "****"
