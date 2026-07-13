from __future__ import annotations

from web.account_service import _api_code


def test_api_code_handles_non_numeric() -> None:
    assert _api_code({"code": "oops"}) == -1
    assert _api_code({"code": None}) == -1
    assert _api_code({"code": 0}) == 0
