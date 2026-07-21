from __future__ import annotations

from src.forward_parser import PARSER_VERSION, _normalize_parsed, parse_forward_content

HEIGU_CONTENT = """霜落之声，微不可察❄️
子弹上膛，一触即发🚄
静如霜落，动如闪银

新品轴体，即将上市 ❤️
申请成为你的新本命

关🐷@黑峡谷 
评论+点赞+转发本条动态并带话题 #黑峡谷新品预告
plq随机揪一位谷宝 
速度vs轻音，你更心水哪一款？"""


def test_normalize_parsed_keeps_prize_description() -> None:
    raw = {
        "is_lottery": True,
        "prize_description": "新品轴体",
        "winner_count": 1,
        "lottery_time": None,
        "need_follow": True,
        "need_repost": True,
        "need_comment": True,
        "confidence": "medium",
    }
    parsed = _normalize_parsed(raw)
    assert parsed["prize_description"] == "新品轴体"
    assert parsed["lottery_time"] is None
    assert parsed["parser_version"] == PARSER_VERSION


def test_normalize_parsed_lottery_time_strict_format() -> None:
    ok = _normalize_parsed(
        {
            "is_lottery": True,
            "prize_description": "月卡",
            "winner_count": 1,
            "lottery_time": "2026-07-24 20:00",
            "need_follow": True,
            "need_repost": True,
            "need_comment": False,
            "confidence": "high",
        }
    )
    assert ok["lottery_time"] == "2026-07-24 20:00"

    bad = _normalize_parsed(
        {
            "is_lottery": True,
            "prize_description": "月卡",
            "winner_count": 1,
            "lottery_time": "7月24日晚8点",
            "need_follow": True,
            "need_repost": True,
            "need_comment": False,
            "confidence": "high",
        }
    )
    assert bad["lottery_time"] is None


def test_parse_forward_content_implicit_product_prize(monkeypatch) -> None:
    def fake_chat_json(*, system: str, user: str, config=None):
        assert "宣发+抽奖一体" in system
        assert "YYYY-MM-DD HH:mm" in system
        assert HEIGU_CONTENT in user
        return {
            "is_lottery": True,
            "prize_description": "新品轴体",
            "winner_count": 1,
            "lottery_time": None,
            "need_follow": True,
            "need_repost": True,
            "need_comment": True,
            "confidence": "medium",
        }

    monkeypatch.setattr("src.forward_parser.chat_json", fake_chat_json)
    parsed = parse_forward_content("1225091549491101701", HEIGU_CONTENT)
    assert parsed["is_lottery"] is True
    assert parsed["prize_description"] == "新品轴体"
    assert parsed["winner_count"] == 1
    assert parsed["lottery_time"] is None


def test_parse_forward_content_vague_prize_stays_empty(monkeypatch) -> None:
    content = "关注并转发，随机揪一位幸运儿，福利见图"

    def fake_chat_json(*, system: str, user: str, config=None):
        return {
            "is_lottery": True,
            "prize_description": "",
            "winner_count": 1,
            "lottery_time": None,
            "need_follow": True,
            "need_repost": True,
            "need_comment": False,
            "confidence": "low",
        }

    monkeypatch.setattr("src.forward_parser.chat_json", fake_chat_json)
    parsed = parse_forward_content("999", content)
    assert parsed["prize_description"] == ""
