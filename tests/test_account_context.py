from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.account_context import (
    AccountContext,
    AccountContextUnavailable,
    capture_current_account_context,
)
from src.bilibili_client import BilibiliClient


def _cookie(uid: int) -> str:
    return f"DedeUserID={uid}; bili_jct=csrf-{uid}; SESSDATA=session-{uid}"


def test_capture_context_is_frozen_and_does_not_repr_secrets(
    isolated_home: Path,
) -> None:
    cookie = _cookie(123456)
    cookie_path = isolated_home / "config" / "cookies.txt"
    cookie_path.write_text(cookie, encoding="utf-8")

    context = capture_current_account_context(expected_uid=123456)

    assert context.uid == 123456
    assert context.csrf == "csrf-123456"
    assert context.cookie_fingerprint
    assert "csrf-123456" not in repr(context)
    assert "session-123456" not in repr(context)
    with pytest.raises(FrozenInstanceError):
        context.uid = 2  # type: ignore[misc]


def test_capture_context_fails_closed_on_cookie_uid_mismatch(
    isolated_home: Path,
) -> None:
    (isolated_home / "config" / "cookies.txt").write_text(
        _cookie(123456),
        encoding="utf-8",
    )

    with pytest.raises(AccountContextUnavailable, match="mismatch"):
        capture_current_account_context(expected_uid=654321)


def test_client_uses_captured_cookie_and_proxy_without_reresolving(
    isolated_home: Path,
) -> None:
    _ = isolated_home
    context = AccountContext(
        uid=123456,
        cookie=_cookie(123456),
        csrf="csrf-123456",
        proxy_url="http://proxy.example:18080",
    )
    fake_http = MagicMock()

    with patch("src.bilibili_client.httpx.Client", return_value=fake_http) as client_cls:
        client = BilibiliClient(account_context=context, warmup=False)

    client_cls.assert_called_once()
    kwargs = client_cls.call_args.kwargs
    assert kwargs["proxy"] == "http://proxy.example:18080"
    assert kwargs["headers"]["Cookie"] == _cookie(123456)
    assert client.login_uid == 123456
    assert client.require_login() == ("csrf-123456", 123456)
    client.close()
