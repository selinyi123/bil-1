from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.lottery_actions import ActionResult
from src.participation import participate_reserve_lottery


def _reserve_info(*, sender_uid: int | None = 999001) -> dict:
    return {
        "reserve_id": 12345,
        "reserve_total": 100,
        "button_status": 1,
        "title": "直播预约",
        "sender_uid": sender_uid,
        "referer": "https://www.bilibili.com/opus/100000000000000001",
    }


def test_participate_reserve_lottery_follow_then_reserve() -> None:
    client = MagicMock()
    steps: list[tuple[int, int, str, str]] = []

    with (
        patch("src.participation.fetch_notice_for_reserve", return_value=None),
        patch("src.participation._resolve_reserve_info", return_value=_reserve_info()),
        patch("src.participation.is_following", return_value=False),
        patch("src.participation.require_login", return_value=("csrf", 1)),
        patch(
            "src.participation.follow_user",
            return_value=ActionResult("follow", True, "uid=999001"),
        ) as follow_mock,
        patch(
            "src.participation._reserve_click",
            return_value=ActionResult("reserve", True, "预约成功"),
        ) as reserve_mock,
        patch("src.participation.time.sleep") as sleep_mock,
        patch("src.participation._persist_result"),
    ):
        result = participate_reserve_lottery(
            client,
            dynamic_id="100000000000000001",
            persist=False,
            on_step=lambda step, total, message, action: steps.append((step, total, message, action)),
        )

    assert result.status == "joined"
    assert [item.action for item in result.actions] == ["follow", "reserve"]
    assert all(item.ok for item in result.actions)
    assert steps == [
        (1, 2, "正在关注（1/2）", "follow"),
        (2, 2, "正在预约（2/2）", "reserve"),
    ]
    follow_mock.assert_called_once()
    reserve_mock.assert_called_once()
    sleep_mock.assert_called_once()


def test_participate_reserve_lottery_skips_follow_when_already_following() -> None:
    client = MagicMock()

    with (
        patch("src.participation.fetch_notice_for_reserve", return_value=None),
        patch("src.participation._resolve_reserve_info", return_value=_reserve_info()),
        patch("src.participation.is_following", return_value=True),
        patch("src.participation.require_login", return_value=("csrf", 1)),
        patch("src.participation.follow_user") as follow_mock,
        patch(
            "src.participation._reserve_click",
            return_value=ActionResult("reserve", True, "预约成功"),
        ),
        patch("src.participation.time.sleep"),
        patch("src.participation._persist_result"),
    ):
        result = participate_reserve_lottery(
            client,
            dynamic_id="100000000000000001",
            persist=False,
        )

    assert result.status == "joined"
    assert result.actions[0].action == "follow"
    assert result.actions[0].ok is True
    assert "已关注" in result.actions[0].detail
    follow_mock.assert_not_called()


def test_participate_reserve_lottery_stops_when_follow_fails() -> None:
    client = MagicMock()

    with (
        patch("src.participation.fetch_notice_for_reserve", return_value=None),
        patch("src.participation._resolve_reserve_info", return_value=_reserve_info()),
        patch("src.participation.is_following", return_value=False),
        patch("src.participation.require_login", return_value=("csrf", 1)),
        patch(
            "src.participation.follow_user",
            return_value=ActionResult("follow", False, "code=1 关注失败"),
        ),
        patch("src.participation._reserve_click") as reserve_mock,
        patch("src.participation.time.sleep") as sleep_mock,
        patch("src.participation._persist_result"),
    ):
        result = participate_reserve_lottery(
            client,
            dynamic_id="100000000000000001",
            persist=False,
        )

    assert result.status == "failed"
    assert [item.action for item in result.actions] == ["follow"]
    assert result.actions[0].ok is False
    reserve_mock.assert_not_called()
    sleep_mock.assert_not_called()


def test_participate_reserve_lottery_fails_when_reserve_fails_after_follow() -> None:
    client = MagicMock()

    with (
        patch("src.participation.fetch_notice_for_reserve", return_value=None),
        patch("src.participation._resolve_reserve_info", return_value=_reserve_info()),
        patch("src.participation.is_following", return_value=True),
        patch("src.participation.require_login", return_value=("csrf", 1)),
        patch(
            "src.participation._reserve_click",
            return_value=ActionResult("reserve", False, "预约失败"),
        ),
        patch("src.participation.time.sleep"),
        patch("src.participation._persist_result"),
    ):
        result = participate_reserve_lottery(
            client,
            dynamic_id="100000000000000001",
            persist=False,
        )

    assert result.status == "failed"
    assert [item.action for item in result.actions] == ["follow", "reserve"]
    assert result.actions[0].ok is True
    assert result.actions[1].ok is False
    assert result.message == "预约失败"


def test_participate_reserve_lottery_uses_notice_sender_uid_fallback() -> None:
    client = MagicMock()
    notice = {"lottery_id": 1, "sender_uid": 888001, "status": 0, "lottery_time": 9999999999}

    with (
        patch("src.participation.fetch_notice_for_reserve", return_value=(notice, 10, "1")),
        patch("src.participation._resolve_reserve_info", return_value=_reserve_info(sender_uid=None)),
        patch("src.participation.is_following", return_value=True),
        patch("src.participation.require_login", return_value=("csrf", 1)),
        patch(
            "src.participation._reserve_click",
            return_value=ActionResult("reserve", True, "预约成功"),
        ),
        patch("src.participation.time.sleep"),
        patch("src.participation._persist_result"),
    ):
        result = participate_reserve_lottery(
            client,
            dynamic_id="100000000000000001",
            persist=False,
        )

    assert result.status == "joined"
    assert result.context_snapshot.get("sender_uid") == 888001


def test_participate_reserve_lottery_fails_without_sender_uid() -> None:
    client = MagicMock()

    with (
        patch("src.participation.fetch_notice_for_reserve", return_value=None),
        patch("src.participation._resolve_reserve_info", return_value=_reserve_info(sender_uid=None)),
        patch("src.participation.follow_user") as follow_mock,
        patch("src.participation._reserve_click") as reserve_mock,
        patch("src.participation._persist_result"),
    ):
        result = participate_reserve_lottery(
            client,
            dynamic_id="100000000000000001",
            persist=False,
        )

    assert result.status == "failed"
    assert "UID" in result.message
    assert result.actions == []
    follow_mock.assert_not_called()
    reserve_mock.assert_not_called()


def test_participate_reserve_lottery_follow_network_error_becomes_failed_action() -> None:
    client = MagicMock()

    with (
        patch("src.participation.fetch_notice_for_reserve", return_value=None),
        patch("src.participation._resolve_reserve_info", return_value=_reserve_info()),
        patch("src.participation.is_following", side_effect=RuntimeError("网络中断")),
        patch("src.participation.require_login", return_value=("csrf", 1)),
        patch("src.participation._reserve_click") as reserve_mock,
        patch("src.participation.time.sleep") as sleep_mock,
        patch("src.participation._persist_result"),
    ):
        result = participate_reserve_lottery(
            client,
            dynamic_id="100000000000000001",
            persist=False,
        )

    assert result.status == "failed"
    assert result.actions[0].action == "follow"
    assert result.actions[0].ok is False
    assert "网络中断" in result.actions[0].detail
    reserve_mock.assert_not_called()
    sleep_mock.assert_not_called()
