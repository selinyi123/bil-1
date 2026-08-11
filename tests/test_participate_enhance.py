"""P2 参与增强测试：抄热评过滤 / @好友与话题 / 乱序 / 随机间隔。"""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from src.lottery_actions import assemble_repost_content
from src.participate_enhance import (
    DEFAULTS,
    EnhanceSettingsModel,
    format_enhance_validation_error,
    load_participate_enhance,
    reset_participate_enhance_cache,
    sanitize_participate_enhance,
)
from src.participate_text import (
    _extract_sender_uid,
    _reply_author_mid,
    _reply_message,
)


def test_assemble_repost_content_plain() -> None:
    content, ctrl = assemble_repost_content("好运连连！")
    assert content == "好运连连！"
    assert json.loads(ctrl) == []


def test_assemble_repost_content_topic_and_at() -> None:
    content, ctrl = assemble_repost_content(
        "好运连连！",
        topic="#每日抽奖#",
        at_users=[{"uid": 294887687, "name": "转发抽奖娘"}],
    )
    assert content.startswith("好运连连！ #每日抽奖#")
    assert "@转发抽奖娘" in content
    parsed = json.loads(ctrl)
    assert len(parsed) == 1
    assert parsed[0]["data"] == "294887687"
    assert parsed[0]["type"] == 1
    # ctrl 定位必须与 content 中 @ 位置一致
    pos = content.find("@转发抽奖娘")
    assert parsed[0]["location"] == pos
    assert parsed[0]["length"] == len("转发抽奖娘") + 1


def test_assemble_repost_content_truncate_keeps_valid_at() -> None:
    base = "长" * 240
    content, ctrl = assemble_repost_content(base, at_users=[{"uid": 1, "name": "好友"}])
    assert len(content) == 233
    parsed = json.loads(ctrl)
    # 截断后 @好友 可能被截掉，此时 ctrl 必须为空（不允许悬空定位）
    if "@好友" in content:
        assert len(parsed) == 1 and parsed[0]["location"] == content.find("@好友")
    else:
        assert parsed == []


def test_assemble_repost_content_same_name_in_base() -> None:
    """base_text 已含同名 @ 时，ctrl 定位必须指向追加的 @ 而非 base 里的。"""
    base = "转发 @好友 的动态"
    content, ctrl = assemble_repost_content(base, at_users=[{"uid": 5, "name": "好友"}])
    parsed = json.loads(ctrl)
    assert len(parsed) == 1
    assert parsed[0]["location"] == len(base) + 1  # 追加处（空格后）
    assert content[parsed[0]["location"]] == "@"
    assert parsed[0]["data"] == "5"


def test_assemble_repost_content_skips_at_when_no_space() -> None:
    """剩余空间不足时跳过 @，绝不追加残缺 @ 或悬空 ctrl。"""
    base = "长" * 232
    content, ctrl = assemble_repost_content(base, at_users=[{"uid": 1, "name": "好友"}])
    assert "@好友" not in content
    assert json.loads(ctrl) == []


def test_reply_extractors() -> None:
    reply = {
        "member": {"mid": 123},
        "content": {"message": "这是热评"},
    }
    assert _reply_message(reply) == "这是热评"
    assert _reply_author_mid(reply) == 123
    assert _reply_author_mid({"member": {"mid": "abc"}}) is None


def test_extract_sender_uid() -> None:
    item = {"modules": {"module_author": {"mid": 456}}}
    assert _extract_sender_uid(item) == 456
    item_list = {"modules": [{"module_author": {"mid": 789}}]}
    assert _extract_sender_uid(item_list) == 789
    assert _extract_sender_uid({"modules": {}}) is None


def test_participate_enhance_defaults(isolated_home) -> None:
    reset_participate_enhance_cache()
    cfg = load_participate_enhance()
    assert cfg["copy_chat"]["enabled"] is False
    assert cfg["copy_chat"]["exclude_author"] is True
    assert cfg["at_users"] == []
    assert cfg["shuffle_targets"] is True
    assert cfg["action_interval_sec"]["min"] == 0.75


def test_participate_enhance_merge(isolated_home, monkeypatch) -> None:
    import src.participate_enhance as module

    config_dir = isolated_home / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "participate_enhance.json").write_text(
        json.dumps({"topic": "#抽奖#", "at_users": [{"uid": 1, "name": "A"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "config_dir", lambda: config_dir)
    reset_participate_enhance_cache()
    cfg = load_participate_enhance()
    assert cfg["topic"] == "#抽奖#"
    assert cfg["at_users"] == [{"uid": 1, "name": "A"}]
    # 未配置项保持默认
    assert cfg["copy_chat"]["enabled"] is False
    assert DEFAULTS["action_interval_sec"]["min"] == 0.75


# ---------- 强类型校验（EnhanceSettingsModel） ----------

VALID_CONFIG: dict = {
    "copy_chat": {"enabled": True, "blockwords": ["抽奖", "互关"], "exclude_author": False},
    "at_users": [{"uid": "294887687", "name": "转发抽奖娘"}, {"uid": 123, "name": "好友"}],
    "topic": "#每日抽奖#",
    "shuffle_targets": True,
    "action_interval_sec": {"min": 0.75, "max": 2.25},
    "partition": {"enabled": True, "name": "抽奖临时关注"},
}


def test_enhance_model_valid_roundtrip() -> None:
    """合法完整配置通过校验，且 dump 后再次校验保持不变。"""
    dumped = EnhanceSettingsModel.model_validate(VALID_CONFIG).model_dump()
    # uid 数字字符串归一化为 int，结构字段一一对应
    assert dumped["at_users"] == [{"uid": 294887687, "name": "转发抽奖娘"}, {"uid": 123, "name": "好友"}]
    assert dumped["copy_chat"] == {"enabled": True, "blockwords": ["抽奖", "互关"], "exclude_author": False}
    assert dumped["topic"] == "#每日抽奖#"
    assert dumped["shuffle_targets"] is True
    assert dumped["action_interval_sec"] == {"min": 0.75, "max": 2.25}
    assert dumped["partition"] == {"enabled": True, "name": "抽奖临时关注"}
    # roundtrip：dump 结果再次通过校验且不变
    assert EnhanceSettingsModel.model_validate(dumped).model_dump() == dumped


def test_enhance_model_partial_input_uses_defaults() -> None:
    """部分提交：缺省字段补默认值（PUT 是合并语义）。"""
    dumped = EnhanceSettingsModel.model_validate({"topic": "#抽奖#"}).model_dump()
    assert dumped["topic"] == "#抽奖#"
    assert dumped["copy_chat"] == {"enabled": False, "blockwords": [], "exclude_author": True}
    assert dumped["at_users"] == []
    assert dumped["shuffle_targets"] is True
    assert dumped["partition"] == {"enabled": False, "name": "抽奖临时关注"}


def test_enhance_model_dedupes_at_users() -> None:
    """at_users 按 uid 去重，保留首个出现的条目。"""
    dumped = EnhanceSettingsModel.model_validate(
        {"at_users": [{"uid": "1", "name": "A"}, {"uid": 1, "name": "B"}, {"uid": "2", "name": "C"}]}
    ).model_dump()
    assert dumped["at_users"] == [{"uid": 1, "name": "A"}, {"uid": 2, "name": "C"}]


def test_enhance_model_unknown_fields_rejected() -> None:
    """未知字段（如 shuffle_target 拼写错误）直接校验失败，不再静默吞掉。"""
    with pytest.raises(ValidationError) as excinfo:
        EnhanceSettingsModel.model_validate({"topic": "#抽奖#", "shuffle_target": True})
    message = format_enhance_validation_error(excinfo.value)
    assert "shuffle_target" in message
    assert "未知字段" in message

    # 嵌套对象内的未知字段同样拒绝
    with pytest.raises(ValidationError):
        EnhanceSettingsModel.model_validate({"copy_chat": {"enabled": True, "bogus_key": 1}})


def test_sanitize_tolerates_unknown_fields_in_disk_config() -> None:
    """磁盘容错加载路径保持宽容：含未知字段的旧配置静默丢弃未知字段，不抛错。"""
    raw = {
        "topic": "#抽奖#",
        "shuffle_target": True,  # typo：模型已 forbid，但 sanitize 必须容忍
        "future_feature": {"x": 1},
    }
    cfg = sanitize_participate_enhance(raw)
    assert cfg["topic"] == "#抽奖#"
    assert "shuffle_target" not in cfg
    assert "future_feature" not in cfg
    assert set(cfg) == set(DEFAULTS)


@pytest.mark.parametrize(
    ("payload", "field", "keyword"),
    [
        # 间隔范围：min > max
        ({"action_interval_sec": {"min": 5, "max": 2}}, "action_interval_sec", "不能大于"),
        # 间隔上限：max 超 600 秒
        ({"action_interval_sec": {"max": 86400}}, "action_interval_sec", "600"),
        # 间隔下界：min <= 0
        ({"action_interval_sec": {"min": 0}}, "action_interval_sec.min", "0"),
        ({"action_interval_sec": {"min": -1}}, "action_interval_sec.min", "0"),
        # at_users 超限（51 个）
        ({"at_users": [{"uid": i, "name": f"u{i}"} for i in range(51)]}, "at_users", "50"),
        # at_users 非数字 uid
        ({"at_users": [{"uid": "abc", "name": "x"}]}, "at_users", "纯数字"),
        ({"at_users": [{"uid": 0, "name": "x"}]}, "at_users", "纯数字"),
        # at_users 不是列表
        ({"at_users": {"uid": 1, "name": "x"}}, "at_users", "列表"),
        # blockwords 超长单条（101 字符）
        ({"copy_chat": {"blockwords": ["长" * 101]}}, "copy_chat.blockwords", "100"),
        # blockwords 数量超限（201 条）
        ({"copy_chat": {"blockwords": ["w"] * 201}}, "copy_chat.blockwords", "200"),
        # 类型错误：布尔字段传字符串/数字
        ({"copy_chat": {"enabled": "yes"}}, "copy_chat.enabled", "布尔"),
        ({"shuffle_targets": "true"}, "shuffle_targets", "布尔"),
        ({"partition": {"enabled": 1}}, "partition.enabled", "布尔"),
        # 类型错误：字符串字段传数字
        ({"topic": 123}, "topic", "字符串"),
        ({"partition": {"name": 42}}, "partition.name", "字符串"),
        ({"at_users": [{"uid": 1, "name": 9}]}, "at_users", "字符串"),
        # 类型错误：数字字段传字符串
        ({"action_interval_sec": {"min": "abc"}}, "action_interval_sec.min", "数字"),
        # 嵌套对象传非对象
        ({"copy_chat": "on"}, "copy_chat", "对象"),
        ({"action_interval_sec": None}, "action_interval_sec", "对象"),
        # 字符串超长
        ({"topic": "长" * 101}, "topic", "长度"),
    ],
)
def test_enhance_model_rejects_invalid(payload: dict, field: str, keyword: str) -> None:
    with pytest.raises(ValidationError) as excinfo:
        EnhanceSettingsModel.model_validate(payload)
    message = format_enhance_validation_error(excinfo.value)
    assert field in message  # 指出哪个字段
    assert keyword in message  # 指出为什么


def test_enhance_model_rejects_invalid_name_too_long() -> None:
    with pytest.raises(ValidationError):
        EnhanceSettingsModel.model_validate({"at_users": [{"uid": 1, "name": "长" * 51}]})


def test_sanitize_tolerates_invalid_disk_config() -> None:
    """磁盘旧配置含非法字段：sanitize 静默回退默认，合法字段保留，不抛错。"""
    raw = {
        "copy_chat": {"enabled": "yes", "blockwords": ["长" * 101], "exclude_author": True},
        "at_users": [{"uid": "abc"}, {"uid": 1, "name": "A"}],
        "topic": 123,
        "shuffle_targets": True,  # 合法字段
        "action_interval_sec": {"min": 86400, "max": 999999},
    }
    cfg = sanitize_participate_enhance(raw)
    # 非法字段回退默认
    assert cfg["copy_chat"] == {"enabled": False, "blockwords": [], "exclude_author": True}
    assert cfg["at_users"] == []
    assert cfg["topic"] == ""
    assert cfg["action_interval_sec"] == {"min": 0.75, "max": 2.25}
    # 合法字段保留
    assert cfg["shuffle_targets"] is True
    # 结构完整（含全部默认字段）
    assert set(cfg) == set(DEFAULTS)


def test_sanitize_tolerates_non_dict() -> None:
    assert sanitize_participate_enhance(None) == DEFAULTS
    assert sanitize_participate_enhance([1, 2]) == DEFAULTS
    assert sanitize_participate_enhance("nope") == DEFAULTS


def test_load_tolerates_invalid_disk_config(isolated_home, monkeypatch) -> None:
    """磁盘上非法旧配置 load 不崩溃（GET 可用），非法字段回退默认。"""
    import src.participate_enhance as module

    config_dir = isolated_home / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "participate_enhance.json").write_text(
        json.dumps(
            {
                "action_interval_sec": {"min": 86400, "max": 999999},
                "topic": 123,
                "copy_chat": {"enabled": "yes"},
                "at_users": [{"uid": "abc"}],
                "shuffle_targets": True,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "config_dir", lambda: config_dir)
    reset_participate_enhance_cache()
    cfg = load_participate_enhance()
    assert cfg["action_interval_sec"] == {"min": 0.75, "max": 2.25}
    assert cfg["topic"] == ""
    assert cfg["copy_chat"]["enabled"] is False
    assert cfg["at_users"] == []
    assert cfg["shuffle_targets"] is True  # 合法字段保留
