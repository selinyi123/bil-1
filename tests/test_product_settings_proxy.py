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


def test_proxy_mask_never_echoes_credentials() -> None:
    masked = _mask_proxy_url("http://alice:top-secret@proxy.example.com:8080/path?token=secret")
    assert masked == "http://***@proxy.example.com:8080/path"
    assert "alice" not in masked
    assert "top-secret" not in masked
    assert "token=secret" not in masked


def test_account_proxy_payload_masks_secret_and_reports_account_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BINGGO_HOME", str(tmp_path))
    monkeypatch.delenv("BINGGO_PROXY", raising=False)
    proxy = "http://alice:top-secret@proxy.example.com:8080"
    _seed_account(tmp_path, proxy=proxy)

    payload = _proxy_payload(UID)

    assert get_account_proxy(UID) == proxy
    assert payload["editable"] is True
    assert payload["effective_source"] == "account"
    assert payload["account_configured"] is True
    assert "top-secret" not in str(payload)
    assert payload["account_proxy"] == "http://***@proxy.example.com:8080"


def test_environment_proxy_wins_without_exposing_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BINGGO_HOME", str(tmp_path))
    _seed_account(tmp_path, proxy="http://account-user:account-pass@account.example.com:8080")
    monkeypatch.setenv("BINGGO_PROXY", "http://env-user:env-pass@env.example.com:7890")

    payload = _proxy_payload(UID)

    assert payload["effective_source"] == "environment"
    assert payload["env_override"] is True
    assert payload["effective_proxy"] == "http://***@env.example.com:7890"
    assert "env-pass" not in str(payload)
    assert "account-pass" not in str(payload)


def test_clear_account_proxy_restores_inheritance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BINGGO_HOME", str(tmp_path))
    monkeypatch.delenv("BINGGO_PROXY", raising=False)
    _seed_account(tmp_path)
    (tmp_path / "config" / "proxy.json").write_text(
        json.dumps({"url": "http://global-user:global-pass@global.example.com:3128"}),
        encoding="utf-8",
    )

    assert set_account_proxy(UID, "http://account.example.com:8080") is True
    assert _proxy_payload(UID)["effective_source"] == "account"
    assert set_account_proxy(UID, None) is True

    payload = _proxy_payload(UID)
    assert payload["effective_source"] == "global"
    assert payload["account_configured"] is False
    assert payload["effective_proxy"] == "http://***@global.example.com:3128"
    assert "global-pass" not in str(payload)
