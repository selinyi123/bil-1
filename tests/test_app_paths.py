from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.app_paths import ensure_user_dirs, install_root, is_frozen, user_home


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
    monkeypatch.setenv("APPDATA", r"C:\Users\Demo\AppData\Roaming")
    monkeypatch.setattr("src.app_paths.is_frozen", lambda: True)
    assert user_home() == Path(r"C:\Users\Demo\AppData\Roaming\Binggo")


def test_frozen_portable_user_home(monkeypatch, tmp_path):
    monkeypatch.delenv("BINGGO_HOME", raising=False)
    monkeypatch.setenv("BINGGO_PORTABLE", "1")
    monkeypatch.setattr("src.app_paths.is_frozen", lambda: True)
    monkeypatch.setattr("src.app_paths.bundle_root", lambda: tmp_path)
    assert user_home() == tmp_path


def test_ensure_user_dirs_seeds_examples(monkeypatch, tmp_path):
    monkeypatch.setattr("src.app_paths.user_home", lambda: tmp_path)
    monkeypatch.setattr("src.app_paths.install_root", lambda: ROOT)
    ensure_user_dirs()
    assert (tmp_path / "config" / "cookies.txt.example").exists()
    assert (tmp_path / "config" / "sources.yaml").exists()
    assert (tmp_path / "data" / "logs").is_dir()


def test_is_frozen_false_in_pytest():
    assert is_frozen() is False
    assert install_root() == ROOT
