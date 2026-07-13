from __future__ import annotations

import pytest

from src.llm_settings import _resolve_base_url, mask_api_key


def test_mask_api_key() -> None:
    assert mask_api_key("") == ""
    assert mask_api_key("short") == "****"
    assert mask_api_key("abcdefghijklmnop") == "abcd****mnop"


def test_resolve_base_url_default() -> None:
    assert _resolve_base_url("") == "https://www.autodl.art/api/v1"


def test_resolve_base_url_valid() -> None:
    assert _resolve_base_url("https://api.example.com/v1") == "https://api.example.com/v1"


@pytest.mark.parametrize("bad_url", ["file:///etc/passwd", "ftp://example.com", "not-a-url"])
def test_resolve_base_url_rejects_invalid(bad_url: str) -> None:
    with pytest.raises(ValueError):
        _resolve_base_url(bad_url)
