from __future__ import annotations

import os
import stat
import sys

import pytest

from src.secure_files import harden_file_permissions, write_text_secret


def test_write_text_secret_atomic(tmp_path) -> None:
    path = tmp_path / "cookies.txt"
    write_text_secret(path, "SESSDATA=a; bili_jct=b")
    assert path.read_text(encoding="utf-8") == "SESSDATA=a; bili_jct=b"
    assert not path.with_name("cookies.txt.tmp").exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX chmod only")
def test_harden_permissions_posix(tmp_path) -> None:
    path = tmp_path / "secret.env"
    path.write_text("x=1", encoding="utf-8")
    os.chmod(path, 0o644)
    assert harden_file_permissions(path) is True
    mode = path.stat().st_mode & 0o777
    assert mode & (stat.S_IRGRP | stat.S_IROTH | stat.S_IWGRP | stat.S_IWOTH) == 0


def test_harden_missing_file(tmp_path) -> None:
    assert harden_file_permissions(tmp_path / "missing.txt") is False
