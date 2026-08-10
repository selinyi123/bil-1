"""P2 参与增强测试：抄热评过滤 / @好友与话题 / 乱序 / 随机间隔。"""
from __future__ import annotations

import json

from src.lottery_actions import assemble_repost_content
from src.participate_enhance import DEFAULTS, load_participate_enhance, reset_participate_enhance_cache
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
