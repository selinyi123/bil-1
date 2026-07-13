from __future__ import annotations

import pytest

from src.sources.common import (
    is_valid_dynamic_id,
    normalize_activity_id,
    normalize_activity_url,
    opus_link,
)


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.bilibili.com/opus/1220298825599549447", "1220298825599549447"),
        ("https://t.bilibili.com/1220298825599549447", "1220298825599549447"),
        ("https://example.com/foo", None),
        ("", None),
        ("opus/123", None),
    ],
)
def test_normalize_activity_id(url: str, expected: str | None) -> None:
    assert normalize_activity_id(url) == expected


def test_normalize_activity_url() -> None:
    assert normalize_activity_url("https://t.bilibili.com/1220298825599549447") == opus_link(
        "1220298825599549447"
    )


@pytest.mark.parametrize(
    "dynamic_id,valid",
    [
        ("1220298825599549447", True),
        ("123456789012345678", True),
        ("1234567890123456789", True),
        ("abc", False),
        ("", False),
        ("123", False),
        ("1220298825599549447;drop", False),
    ],
)
def test_is_valid_dynamic_id(dynamic_id: str, valid: bool) -> None:
    assert is_valid_dynamic_id(dynamic_id) is valid
