from __future__ import annotations

from src.version_info import compare_versions, get_version, parse_version


def test_get_version_matches_app_paths() -> None:
    from src.app_paths import __version__

    assert get_version() == __version__


def test_parse_version_basic() -> None:
    assert parse_version("4.0.2") == (4, 0, 2)
    assert parse_version("v4.0.2") == (4, 0, 2)
    assert parse_version("V1.2.3") == (1, 2, 3)
    assert parse_version("1.2.3-rc.1") == (1, 2, 3)
    assert parse_version("") is None
    assert parse_version("abc") is None
    assert parse_version("1.2") is None


def test_strip_v_prefix_does_not_eat_letters() -> None:
    from src.version_info import strip_v_prefix

    assert strip_v_prefix("v4.0.2") == "4.0.2"
    assert strip_v_prefix("Version1") == "Version1"


def test_compare_versions() -> None:
    assert compare_versions("4.0.2", "4.0.3") == -1
    assert compare_versions("4.0.3", "4.0.2") == 1
    assert compare_versions("4.0.2", "v4.0.2") == 0
    assert compare_versions("bad", "also-bad") is None
    assert compare_versions("same-tag", "same-tag") == 0
