from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import text
from sqlmodel import Session, SQLModel

from src.db.engine import db_path, get_engine
from src.db.models import SchemaMeta

# 确保全部表注册到 metadata
from src.db import models as _models  # noqa: F401

SCHEMA_VERSION = 4

_JOB_V2_COLUMNS: tuple[tuple[str, str], ...] = (
    ("label", "TEXT NOT NULL DEFAULT ''"),
    ("source", "TEXT NOT NULL DEFAULT 'ui'"),
    ("params_json", "TEXT NOT NULL DEFAULT '{}'"),
    ("result_json", "TEXT"),
    ("error_kind", "TEXT"),
)


def migrate_v1_to_v2(session: Session) -> None:
    """为已有 jobs 表补齐 v2 列与索引；列已存在则跳过（幂等）。"""
    conn = session.connection()
    table_exists = conn.execute(
        text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='jobs'")
    ).fetchone()
    if table_exists is None:
        # create_all 应已建表；若仍无表则交由下轮 create_all/启动失败暴露
        return
    existing = {
        str(row[1])
        for row in conn.execute(text("PRAGMA table_info(jobs)")).fetchall()
    }
    for name, decl in _JOB_V2_COLUMNS:
        if name not in existing:
            conn.execute(text(f"ALTER TABLE jobs ADD COLUMN {name} {decl}"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_jobs_state ON jobs(state)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_jobs_finished_at ON jobs(finished_at)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_jobs_created_at ON jobs(created_at)"))


def migrate_v2_to_v3(session: Session) -> None:
    """v3：account_profile_cache 由单例行改为按 uid 主键。

    缓存内容可安全重建（网络失败时的回退展示），因此直接 drop 旧表，
    新表结构由 init_db 末尾的 create_all 按当前模型重建。
    """
    conn = session.connection()
    conn.execute(text("DROP TABLE IF EXISTS account_profile_cache"))


def migrate_v3_to_v4(session: Session) -> None:
    """v4：为 jobs 持久化服务端绑定的账号 UID，旧任务保持 NULL。"""
    conn = session.connection()
    table_exists = conn.execute(
        text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='jobs'")
    ).fetchone()
    if table_exists is None:
        return
    existing = {
        str(row[1])
        for row in conn.execute(text("PRAGMA table_info(jobs)"))
    }
    if "account_uid" not in existing:
        conn.execute(text("ALTER TABLE jobs ADD COLUMN account_uid TEXT"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_jobs_account_uid ON jobs(account_uid)"))


_MIGRATIONS: dict[int, Callable[[Session], None]] = {
    1: migrate_v1_to_v2,
    2: migrate_v2_to_v3,
    3: migrate_v3_to_v4,
}


def _schema_newer_than_code_error(recorded: int) -> RuntimeError:
    from src.db.engine import db_path

    db = db_path()
    return RuntimeError(
        f"数据库 schema_version={recorded} 高于本程序支持的 {SCHEMA_VERSION}，无法安全启动。\n\n"
        f"数据库文件：{db}\n\n"
        "请先安装最新版 Release，并完全退出 Binggo（任务管理器结束所有 Binggo.exe）后重试。\n"
        "若仍失败：备份上述 data 文件夹后删除 binggo.db，再启动（会丢失本地活动库，Cookie 仍在 config）。"
    )


def _table_exists(engine, name: str) -> bool:
    with engine.connect() as conn:
        return (
            conn.execute(
                text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:name"),
                {"name": name},
            ).fetchone()
            is not None
        )


def _session_table_exists(session: Session, name: str) -> bool:
    """在既有事务连接内探测业务表是否存在（避免额外开连接/死锁风险）。"""
    conn = session.connection()
    return (
        conn.execute(
            text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:name"),
            {"name": name},
        ).fetchone()
        is not None
    )


def init_db() -> None:
    """创建表结构并执行 schema_version 迁移。可重复调用。

    顺序保证（forward-compat 不变量，P1）：
    1. 原生 SQL 探测 schema_meta 表（不经过 ORM，此阶段零写）；
    2. 表不存在 → 全新库：create_all + 写入当前版本；
    3. meta 版本高于代码 → 直接 hard fail —— 在此之前不执行任何写操作，
       也绝不把未来版本"纠正"回旧版本；
    4. 版本低于代码 → 顺序执行迁移，逐级递增版本；
    5. 末尾 create_all 幂等补建迁移未覆盖的缺失表/索引。
    """
    engine = get_engine()
    if not _table_exists(engine, "schema_meta"):
        # 全新库：先建表再写版本号（此时无任何旧数据可破坏）
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            session.add(SchemaMeta(id=1, version=SCHEMA_VERSION))
            session.commit()
        return

    with Session(engine) as session:
        row = session.get(SchemaMeta, 1)
        if row is None:
            # 异常态：meta 表存在但无记录。若已有业务表则说明是元数据损坏的
            # 旧库——fail-closed 拒绝启动，绝不把旧库错误标记为最新版本；
            # 若确认无任何业务表（真全新库/半初始化）→ 正常补齐并建表。
            for table in ("jobs", "activities"):
                if _session_table_exists(session, table):
                    raise RuntimeError(
                        f"数据库 schema_meta 元数据缺失但存在业务表（{table}），"
                        "元数据已损坏，拒绝启动。\n\n"
                        f"数据库文件：{db_path()}\n\n"
                        "请备份 data 文件夹后删除 binggo.db 再启动，"
                        "或先安装最新版 Release 后重试。"
                    )
            session.add(SchemaMeta(id=1, version=SCHEMA_VERSION))
            session.commit()
        else:
            current = int(row.version)
            if current > SCHEMA_VERSION:
                # 未来版本：在任何写操作之前拒绝打开
                raise _schema_newer_than_code_error(current)
            while current < SCHEMA_VERSION:
                migrate = _MIGRATIONS.get(current)
                if migrate is None:
                    raise RuntimeError(f"缺少 schema 迁移：{current} -> {current + 1}")
                migrate(session)
                current += 1
                meta = session.get(SchemaMeta, 1)
                if meta is None:
                    session.add(SchemaMeta(id=1, version=current))
                else:
                    meta.version = current
                session.commit()

    # 迁移完成后补建缺失表/索引（幂等；对"刚迁移完"的库是安全的）
    SQLModel.metadata.create_all(engine)
