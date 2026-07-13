from __future__ import annotations

from src.lottery_classifier import _is_upower_lottery


def test_upower_lottery_detected_from_additional() -> None:
    additional = {"type": "ADDITIONAL_TYPE_UPOWER_LOTTERY", "upower_lottery": {"foo": 1}}
    assert _is_upower_lottery(additional) is True


def test_upower_lottery_not_detected_for_normal_interact() -> None:
    additional = {"type": "ADDITIONAL_TYPE_LOTTERY", "lottery": {"id": 1}}
    assert _is_upower_lottery(additional) is False
