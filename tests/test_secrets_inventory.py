from __future__ import annotations

from src.secrets_inventory import (
    SECRET_FILENAMES,
    is_redact_secret_key,
    is_sanitize_secret_key,
    redact_secret_key_re,
    sanitize_secret_key_re,
    secret_filenames_csv,
    secret_file_paths,
)


def test_secret_filenames() -> None:
    assert SECRET_FILENAMES == frozenset({"cookies.txt", "llm.env"})
    assert "cookies.txt" in secret_filenames_csv()


def test_secrets_inventory_paths_follow_home(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("src.app_paths.user_home", lambda: tmp_path)
    paths = secret_file_paths()
    assert paths[0] == tmp_path / "config" / "cookies.txt"
    assert paths[1] == tmp_path / "config" / "llm.env"


def test_redact_vs_sanitize_matching() -> None:
    assert is_redact_secret_key("api_key")
    assert is_redact_secret_key("API-KEY")
    assert not is_redact_secret_key("my_cookie")
    assert is_sanitize_secret_key("my_cookie")
    assert redact_secret_key_re().match("cookie")
    assert sanitize_secret_key_re().search("x_token_y")
