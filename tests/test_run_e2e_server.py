"""E2E HOME 隔离守卫。"""

from __future__ import annotations

from pathlib import Path

import pytest

from web.e2e_seed import assert_safe_e2e_home

ROOT = Path(__file__).resolve().parents[1]


def test_reject_repo_root() -> None:
    with pytest.raises(ValueError, match="仓库根"):
        assert_safe_e2e_home(ROOT, ROOT)


def test_reject_repo_data() -> None:
    with pytest.raises(ValueError, match="data"):
        assert_safe_e2e_home(ROOT / "data", ROOT)


def test_reject_under_repo_data() -> None:
    with pytest.raises(ValueError, match="data"):
        assert_safe_e2e_home(ROOT / "data" / "e2e-should-not", ROOT)


def test_accept_temp_home(tmp_path: Path) -> None:
    assert_safe_e2e_home(tmp_path, ROOT)
