from __future__ import annotations

from pathlib import Path

import pytest

from src.source_settings import (
    add_ds10_source,
    get_ds8_dynamic_ids,
    get_ds9_tags,
    list_ds10_entries,
    remove_ds10_source,
    set_ds8_dynamic_ids,
    set_ds9_tags,
    validate_external_source,
)


DYNAMIC_ID = "123456789012345678"


def test_ds8_typed_save_normalizes_links_and_deduplicates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BINGGO_HOME", str(tmp_path))

    saved = set_ds8_dynamic_ids(
        [
            DYNAMIC_ID,
            f"https://www.bilibili.com/opus/{DYNAMIC_ID}?spm_id_from=333.999.0.0",
            DYNAMIC_ID,
        ]
    )

    assert saved == [DYNAMIC_ID]
    assert get_ds8_dynamic_ids() == [DYNAMIC_ID]
    assert (tmp_path / "config" / "manual_dyids.txt").read_text(encoding="utf-8") == f"{DYNAMIC_ID}\n"


def test_ds8_rejects_invalid_dynamic_identifier(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BINGGO_HOME", str(tmp_path))
    with pytest.raises(ValueError, match="动态 ID/链接"):
        set_ds8_dynamic_ids(["not-a-bilibili-dynamic"])


def test_ds9_normalizes_hash_wrapping_and_deduplicates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BINGGO_HOME", str(tmp_path))

    saved = set_ds9_tags(["#抽奖#", " 福利 ", "抽奖"])

    assert saved == ["抽奖", "福利"]
    assert get_ds9_tags() == ["抽奖", "福利"]
    assert (tmp_path / "config" / "topic_tags.txt").read_text(encoding="utf-8") == "抽奖\n福利\n"


def test_ds10_list_never_echoes_path_credentials_or_query_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BINGGO_HOME", str(tmp_path))
    raw = (
        "https://api-user:super-secret@example.com/"
        "secret-path-token/lottery.json?token=token-value&uid=123456"
    )

    created = add_ds10_source(raw)
    entries = list_ds10_entries()

    assert len(entries) == 1
    entry = entries[0]
    assert entry["id"] == created["id"]
    assert entry["kind"] == "https"
    assert entry["display"] == "https://example.com/…?…"
    for secret in (
        "api-user",
        "super-secret",
        "secret-path-token",
        "lottery.json",
        "token-value",
        "123456",
        "token=",
        "uid=",
    ):
        assert secret not in entry["display"]
    assert remove_ds10_source(entry["id"]) is True
    assert list_ds10_entries() == []


def test_ds10_file_display_does_not_echo_local_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    inside = home / "imports" / "private-token-name.json"
    monkeypatch.setenv("BINGGO_HOME", str(home))

    entry = add_ds10_source(inside.as_uri())

    assert entry["display"] == "file://BINGGO_HOME/…"
    assert "private-token-name" not in entry["display"]
    assert str(home) not in entry["display"]


def test_ds10_web_file_source_is_scoped_to_binggo_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    inside = home / "imports" / "lottery.json"
    outside = tmp_path / "outside.json"
    monkeypatch.setenv("BINGGO_HOME", str(home))

    assert validate_external_source(inside.as_uri(), web_safe_file=True) == inside.as_uri()
    with pytest.raises(ValueError, match="BINGGO_HOME"):
        validate_external_source(outside.as_uri(), web_safe_file=True)


def test_ds10_rejects_unsupported_schemes_invalid_ports_and_control_chars(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BINGGO_HOME", str(tmp_path))
    with pytest.raises(ValueError, match="仅支持"):
        validate_external_source("ftp://example.com/data.json")
    with pytest.raises(ValueError, match="端口"):
        validate_external_source("https://example.com:99999/data.json")
    with pytest.raises(ValueError, match="控制字符"):
        validate_external_source("https://example.com/data.json\nX-Test: injected")
