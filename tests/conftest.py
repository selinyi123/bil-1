from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """隔离用户数据目录与 SQLite 引擎，供依赖 DB 的测试使用。"""
    monkeypatch.setenv("BINGGO_HOME", str(tmp_path))
    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"
    data_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "output").mkdir(parents=True, exist_ok=True)
    (data_dir / "cache").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("src.app_paths.USER_HOME", tmp_path)
    monkeypatch.setattr("src.app_paths.DATA_DIR", data_dir)
    monkeypatch.setattr("src.app_paths.CONFIG_DIR", config_dir)
    monkeypatch.setattr("src.app_paths.user_home", lambda: tmp_path)
    # 已建空库，跳过 ensure_user_dirs 的种子 bootstrap，避免污染隔离用例
    monkeypatch.setattr("src.app_paths._SEEDED", True)
    monkeypatch.setattr("src.app_paths._BOOTSTRAPPED", True)

    # 常见 Store 模块级 DATA_DIR 副本
    for mod in (
        "src.state_store",
        "src.activity_store",
        "src.user_data",
        "src.source_outputs",
        "src.watch_sync",
        "web.activity_service",
    ):
        try:
            monkeypatch.setattr(f"{mod}.DATA_DIR", data_dir, raising=False)
        except Exception:
            pass

    from src.db.engine import db_path, reset_engine_for_tests
    from src.db.schema import init_db

    reset_engine_for_tests()
    init_db()
    # 硬隔离：引擎路径必须落在 tmp_path，防止污染开发机真实 binggo.db
    resolved_db = db_path().resolve()
    resolved_home = tmp_path.resolve()
    assert resolved_db.is_relative_to(resolved_home), resolved_db
    # 额外保险：绝不能落到仓库真实 data/binggo.db
    real_db = (ROOT / "data" / "binggo.db").resolve()
    assert resolved_db != real_db, "isolated_home 仍指向仓库真实数据库"
    yield tmp_path
    reset_engine_for_tests()
    assert db_path().resolve().is_relative_to(tmp_path.resolve()), db_path()
