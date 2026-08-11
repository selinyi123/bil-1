from __future__ import annotations

import threading
from pathlib import Path

from sqlalchemy import event
from sqlmodel import Session, create_engine

_engine = None
_engine_db_path: Path | None = None
_engine_lock = threading.Lock()


def db_path() -> Path:
    # 动态解析，便于测试通过 BINGGO_HOME / monkeypatch user_home 隔离库文件
    from src.app_paths import user_home

    return user_home() / "data" / "binggo.db"


def _sqlite_url(path: Path) -> str:
    resolved = path.resolve()
    # SQLAlchemy SQLite absolute path: sqlite:///C:/... on Windows
    return f"sqlite:///{resolved.as_posix()}"


def get_engine():
    """返回全局引擎；若 DATA_DIR/库路径变化则自动重建（避免粘连到旧库）。

    全局 singleton 的创建/dispose/重建由 _engine_lock 串行化，避免多线程
    并发首次调用时重复建引擎或重建竞态。
    """
    global _engine, _engine_db_path
    path = db_path().resolve()
    with _engine_lock:
        if _engine is not None and _engine_db_path is not None and _engine_db_path != path:
            _engine.dispose()
            _engine = None
            _engine_db_path = None
        if _engine is None:
            path.parent.mkdir(parents=True, exist_ok=True)
            _engine = create_engine(
                _sqlite_url(path),
                connect_args={"check_same_thread": False},
                pool_pre_ping=True,
            )
            _engine_db_path = path

            @event.listens_for(_engine, "connect")
            def _on_connect(dbapi_conn, _connection_record) -> None:  # type: ignore[no-untyped-def]
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=5000")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

    return _engine


def reset_engine_for_tests() -> None:
    """测试用：关闭并丢弃全局 engine。"""
    global _engine, _engine_db_path
    with _engine_lock:
        if _engine is not None:
            _engine.dispose()
            _engine = None
        _engine_db_path = None


def new_session() -> Session:
    return Session(get_engine())
