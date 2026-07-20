from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from src.secrets_inventory import SECRET_FILENAMES

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
def test_secret_filenames_not_tracked() -> None:
    if not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    result = subprocess.run(
        ["git", "ls-files", "--", "config/cookies.txt", "config/llm.env"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    tracked = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    assert not tracked, f"敏感文件不应被 git 跟踪: {tracked}"
    # 清单与检查路径一致
    assert SECRET_FILENAMES == frozenset({"cookies.txt", "llm.env"})
