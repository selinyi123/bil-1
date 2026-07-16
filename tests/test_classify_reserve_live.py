from __future__ import annotations

from src.lottery_classifier import (
    _classify_reserve_candidate,
    _is_live_stream_reserve_only,
)


def test_live_stream_reserve_detected_from_jump_url() -> None:
    reserve = {
        "title": "直播预约：测试",
        "jump_url": "https://live.bilibili.com/25623515",
        "desc1": {"text": "今天 20:00 直播"},
        "desc2": {"text": "100人预约"},
    }
    assert _is_live_stream_reserve_only(reserve) is True


def test_live_stream_reserve_detected_from_broadcasting_state() -> None:
    reserve = {
        "title": "直播预约：🐾 叮！3D狗狗即将公开—",
        "jump_url": "https://live.bilibili.com/25623515",
        "desc1": {"text": "直播中"},
        "desc2": {"text": "226人看过"},
        "rid": 5653684,
    }
    assert _is_live_stream_reserve_only(reserve) is True


def test_reserve_lottery_not_detected_as_live_only() -> None:
    reserve = {
        "title": "直播预约：暑假来一场直播？好主意",
        "jump_url": "",
        "desc1": {"text": "今天 20:00 直播"},
        "desc2": {"text": "978人预约"},
        "rid": 5343511,
    }
    assert _is_live_stream_reserve_only(reserve) is False


def test_classify_reserve_candidate_skips_live_only_without_notice(monkeypatch) -> None:
    class _Client:
        pass

    reserve = {
        "title": "直播预约：🐾 叮！3D狗狗即将公开—",
        "jump_url": "https://live.bilibili.com/25623515",
        "desc1": {"text": "直播中"},
        "desc2": {"text": "226人看过"},
        "rid": 5653684,
    }
    monkeypatch.setattr(
        "src.lottery_classifier._has_reserve_lottery_notice",
        lambda client, dynamic_id: False,
    )
    outcome = _classify_reserve_candidate(
        _Client(),
        "1224565879889461267",
        {"reserve": reserve, "type": "ADDITIONAL_TYPE_RESERVE"},
    )
    assert outcome == "skip"


def test_classify_reserve_candidate_keeps_reserve_lottery_with_notice(monkeypatch) -> None:
    class _Client:
        pass

    reserve = {
        "title": "直播预约：暑假来一场直播？好主意",
        "desc1": {"text": "今天 20:00 直播"},
        "desc2": {"text": "978人预约"},
        "rid": 5343511,
    }
    monkeypatch.setattr(
        "src.lottery_classifier._has_reserve_lottery_notice",
        lambda client, dynamic_id: True,
    )
    outcome = _classify_reserve_candidate(
        _Client(),
        "1164836018782732311",
        {"reserve": reserve, "type": "ADDITIONAL_TYPE_RESERVE"},
    )
    assert outcome == "预约抽奖"
