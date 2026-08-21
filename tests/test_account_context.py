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


def test_context_direct_connection_is_not_overridden_by_global_proxy(monkeypatch) -> None:
    """AccountContext 冻结的"明确直连"不得被全局代理兜底穿透。

    构造函数注释明确写着 "The captured proxy is part of the execution identity.
    Do not re-resolve it after a job has started."，但原实现紧接着就
    `if proxy is None: proxy = get_proxy_url(...)` —— proxy_url=None 在 context
    语境下表示"明确直连"，不是"未指定"，重新解析会让冻结承诺失效，
    并可能在任务执行中途改变网络身份。
    """
    import httpx

    from src.bilibili_client import BilibiliClient

    captured: dict[str, object] = {}

    class _FakeClient:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        cookies: dict[str, str] = {}

        def close(self) -> None:
            return None

    monkeypatch.setattr(httpx, "Client", _FakeClient)
    monkeypatch.setattr("src.proxy_config.get_proxy_url", lambda uid=None: "http://global-proxy:8080")

    class _Ctx:
        uid = 111
        cookie = "SESSDATA=x; bili_jct=y; DedeUserID=111"
        csrf = "y"
        proxy_url = None  # 明确直连

    BilibiliClient(warmup=False, account_context=_Ctx())
    assert captured.get("proxy") is None, "context 的明确直连被全局代理覆盖了"


def test_legacy_path_still_resolves_global_proxy(monkeypatch) -> None:
    """无 context 的 legacy 路径行为不变：proxy=None 仍表示"未指定，去解析全局"。"""
    import httpx

    from src.bilibili_client import BilibiliClient

    captured: dict[str, object] = {}

    class _FakeClient:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        cookies: dict[str, str] = {}

        def close(self) -> None:
            return None

    monkeypatch.setattr(httpx, "Client", _FakeClient)
    monkeypatch.setattr("src.proxy_config.get_proxy_url", lambda uid=None: "http://global-proxy:8080")
    monkeypatch.setattr("src.bilibili_client._load_cookie_string", lambda: None)

    BilibiliClient(warmup=False)
    assert captured.get("proxy") == "http://global-proxy:8080"
