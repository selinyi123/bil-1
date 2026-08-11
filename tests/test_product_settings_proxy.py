from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.account_pool import get_account_proxy, set_account_proxy
from web.product_routes import _mask_proxy_url, _proxy_payload, _validate_proxy_url


UID = 123456789


def _seed_account(home: Path, *, proxy: str | None = None) -> None:
    accounts = home / "config" / "accounts"
    accounts.mkdir(parents=True, exist_ok=True)
    (accounts / f"{UID}.txt").write_text("SESSDATA=test; DedeUserID=123456789;", encoding="utf-8")
    if proxy is not None:
        (accounts / f"{UID}.json").write_text(json.dumps({"proxy": proxy}), encoding="utf-8")


def test_proxy_url_validation_accepts_http_https_and_rejects_other_schemes() -> None:
    assert _validate_proxy_url("http://127.0.0.1:7890") == "http://127.0.0.1:7890"
    assert _validate_proxy_url("https://user:pass@proxy.example.com:8443") == "https://user:pass@proxy.example.com:8443"
    with pytest.raises(ValueError, match="仅支持"):
        _validate_proxy_url("socks5://127.0.0.1:1080")
    with pytest.raises(ValueError, match="端口"):
        _validate_proxy_url("http://127.0.0.1:99999")
    with pytest.raises(ValueError, match="控制字符"):
        _validate_proxy_url("http://proxy.example.com:8080\nX-Test: injected")


def test_proxy_mask_returns_origin_only() -> None:
    masked = _mask_proxy_url(
        "http://alice:top-secret@proxy.example.com:8080/secret-path?token=query-secret"
    )
    assert masked == "http://proxy.example.com:8080"
    for secret in ("alice", "top-secret", "secret-path", "query-secret", "token="):
        assert secret not in masked


def test_account_proxy_payload_masks_secret_and_reports_account_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BINGGO_HOME", str(tmp_path))
    monkeypatch.delenv("BINGGO_PROXY", raising=False)
    proxy = "http://alice:top-secret@proxy.example.com:8080/private-token-path"
    _seed_account(tmp_path, proxy=proxy)

    payload = _proxy_payload(UID)

    assert get_account_proxy(UID) == proxy
    assert payload["editable"] is True
    assert payload["effective_source"] == "account"
    assert payload["account_configured"] is True
    assert payload["account_proxy"] == "http://proxy.example.com:8080"
    for secret in ("alice", "top-secret", "private-token-path"):
        assert secret not in str(payload)


def test_environment_proxy_wins_without_exposing_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BINGGO_HOME", str(tmp_path))
    _seed_account(tmp_path, proxy="http://account-user:account-pass@account.example.com:8080/account-secret")
    monkeypatch.setenv("BINGGO_PROXY", "http://env-user:env-pass@env.example.com:7890/env-secret?token=123")

    payload = _proxy_payload(UID)

    assert payload["effective_source"] == "environment"
    assert payload["env_override"] is True
    assert payload["effective_proxy"] == "http://env.example.com:7890"
    for secret in ("env-user", "env-pass", "env-secret", "account-user", "account-pass", "account-secret", "token=123"):
        assert secret not in str(payload)


def test_clear_account_proxy_restores_inheritance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BINGGO_HOME", str(tmp_path))
    monkeypatch.delenv("BINGGO_PROXY", raising=False)
    _seed_account(tmp_path)
    (tmp_path / "config" / "proxy.json").write_text(
        json.dumps({"url": "http://global-user:global-pass@global.example.com:3128/global-secret"}),
        encoding="utf-8",
    )

    assert set_account_proxy(UID, "http://account.example.com:8080") is True
    assert _proxy_payload(UID)["effective_source"] == "account"
    assert set_account_proxy(UID, None) is True

    payload = _proxy_payload(UID)
    assert payload["effective_source"] == "global"
    assert payload["account_configured"] is False
    assert payload["effective_proxy"] == "http://global.example.com:3128"
    for secret in ("global-user", "global-pass", "global-secret"):
        assert secret not in str(payload)
