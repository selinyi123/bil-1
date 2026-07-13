from __future__ import annotations

import pytest

from src.bilibili_login import (
    BilibiliLoginError,
    POLL_SCANNED,
    POLL_SUCCESS,
    POLL_WAITING,
    _poll_status,
    save_cookies,
)


def test_poll_status_prefers_data_code() -> None:
    assert _poll_status({"code": 0, "data": {"code": POLL_WAITING}}) == POLL_WAITING
    assert _poll_status({"code": -1, "data": {"code": POLL_SCANNED}}) == POLL_SCANNED
    assert _poll_status({"code": POLL_SUCCESS, "data": {}}) == POLL_SUCCESS


def test_poll_status_invalid_returns_negative_one() -> None:
    assert _poll_status({}) == -1
    assert _poll_status({"data": {"code": "bad"}}) == -1


def test_save_cookies_rejects_empty(tmp_path, monkeypatch) -> None:
    from src import bilibili_login

    cookie_path = tmp_path / "cookies.txt"
    monkeypatch.setattr(bilibili_login, "COOKIE_PATH", cookie_path)

    with pytest.raises(BilibiliLoginError, match="为空"):
        save_cookies("   ")


def test_save_cookies_writes_atomically(tmp_path, monkeypatch) -> None:
    from src import bilibili_login

    cookie_path = tmp_path / "cookies.txt"
    monkeypatch.setattr(bilibili_login, "COOKIE_PATH", cookie_path)

    saved = save_cookies("SESSDATA=abc; bili_jct=xyz")
    assert saved == cookie_path
    assert cookie_path.read_text(encoding="utf-8") == "SESSDATA=abc; bili_jct=xyz"
    assert not cookie_path.with_suffix(".txt.tmp").exists()
