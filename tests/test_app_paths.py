from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.app_paths import (
    app_bundle_root,
    ensure_user_dirs,
    install_root,
    is_frozen,
    platform_label,
    user_home,
)


def test_user_home_override(monkeypatch, tmp_path):
    monkeypatch.setenv("BINGGO_HOME", str(tmp_path))
    assert user_home() == tmp_path


def test_dev_mode_user_home_is_project_root(monkeypatch):
    monkeypatch.delenv("BINGGO_HOME", raising=False)
    monkeypatch.setattr("src.app_paths.is_frozen", lambda: False)
    assert user_home() == ROOT


def test_frozen_installed_user_home(monkeypatch):
    monkeypatch.delenv("BINGGO_HOME", raising=False)
    monkeypatch.delenv("BINGGO_PORTABLE", raising=False)
    appdata = r"C:\Users\Demo\AppData\Roaming"
    monkeypatch.setenv("APPDATA", appdata)
    monkeypatch.setattr("src.app_paths.is_frozen", lambda: True)
    monkeypatch.setattr(sys, "platform", "win32")
    # 两侧用同一构造，避免 Linux CI 上反斜杠 Path 字面量比较踩坑
    assert user_home() == Path(appdata) / "Binggo"


def test_frozen_portable_user_home(monkeypatch, tmp_path):
    monkeypatch.delenv("BINGGO_HOME", raising=False)
    monkeypatch.setenv("BINGGO_PORTABLE", "1")
    monkeypatch.setattr("src.app_paths.is_frozen", lambda: True)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr("src.app_paths.bundle_root", lambda: tmp_path)
    assert user_home() == tmp_path


def test_frozen_darwin_application_support(monkeypatch, tmp_path):
    monkeypatch.delenv("BINGGO_HOME", raising=False)
    monkeypatch.delenv("BINGGO_PORTABLE", raising=False)
    monkeypatch.setattr("src.app_paths.is_frozen", lambda: True)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert user_home() == tmp_path / "Library" / "Application Support" / "Binggo"


def test_frozen_darwin_portable_uses_app_parent(monkeypatch, tmp_path):
    monkeypatch.delenv("BINGGO_HOME", raising=False)
    monkeypatch.setenv("BINGGO_PORTABLE", "1")
    monkeypatch.setattr("src.app_paths.is_frozen", lambda: True)
    monkeypatch.setattr(sys, "platform", "darwin")
    fake_exe = tmp_path / "Binggo.app" / "Contents" / "MacOS" / "Binggo"
    fake_exe.parent.mkdir(parents=True)
    fake_exe.write_bytes(b"")
    monkeypatch.setattr(sys, "executable", str(fake_exe))
    assert app_bundle_root() == tmp_path / "Binggo.app"
    assert user_home() == tmp_path


def test_platform_label(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assert platform_label() == "windows"
    monkeypatch.setattr(sys, "platform", "darwin")
    assert platform_label() == "macos"


def test_ensure_user_dirs_seeds_examples(monkeypatch, tmp_path):
    monkeypatch.setattr("src.app_paths.user_home", lambda: tmp_path)
    monkeypatch.setattr("src.app_paths.install_root", lambda: ROOT)
    monkeypatch.setattr("src.app_paths._SEEDED", False)
    monkeypatch.setattr("src.app_paths._BOOTSTRAPPED", False)
    from src.db.engine import reset_engine_for_tests

    reset_engine_for_tests()
    ensure_user_dirs()
    assert (tmp_path / "config" / "cookies.txt.example").exists()
    assert (tmp_path / "config" / "sources.yaml").exists()
    assert (tmp_path / "data" / "logs").is_dir()
    reset_engine_for_tests()


def test_is_frozen_false_in_pytest():
    assert is_frozen() is False
    assert install_root() == ROOT


def test_dashboard_assert_loopback() -> None:
    from src.dashboard_server import assert_loopback_host

    assert_loopback_host("127.0.0.1")
    assert_loopback_host("localhost")
    with pytest.raises(RuntimeError, match="loopback"):
        assert_loopback_host("0.0.0.0")
