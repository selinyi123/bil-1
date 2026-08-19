from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.activity_store import activity_count, load_activities, replace_all_activities
from src.db.activity_codec import activity_dict_to_row, row_to_activity_dict
from src.db.engine import db_path, reset_engine_for_tests
from src.db.import_json import EXIT_NONEMPTY, EXIT_SOURCE, ImportError as JsonImportError, run_import
from src.db.schema import SCHEMA_VERSION, init_db
from src.db.session import session_scope
from src.db.models import SchemaMeta
from src.participation_store import load_participations, set_participation
from src.state_store import get_last_container, save_state, set_last_container


def test_init_db_idempotent(isolated_home: Path) -> None:
    init_db()
    init_db()
    with session_scope() as session:
        meta = session.get(SchemaMeta, 1)
        assert meta is not None
        assert int(meta.version) == SCHEMA_VERSION
    assert db_path().exists()
    assert db_path().parent == isolated_home / "data"


def test_migrate_v2_to_v3_rekeys_account_profile_cache(isolated_home: Path) -> None:
    """v3 迁移：account_profile_cache 从单例行重建为按 uid 主键（旧缓存丢弃可安全重建）。"""
    from sqlalchemy import text as sql_text

    from src.db.models import AccountProfileCacheRow

    init_db()
    with session_scope() as session:
        meta = session.get(SchemaMeta, 1)
        assert meta is not None
        # 模拟 v2 库：单例行缓存 + 版本号 2
        session.execute(sql_text("DROP TABLE account_profile_cache"))
        session.execute(
            sql_text(
                "CREATE TABLE account_profile_cache ("
                "id INTEGER PRIMARY KEY, uname TEXT, face TEXT, mid INTEGER, "
                "following INTEGER, dynamic_count INTEGER, updated_at INTEGER, raw_json TEXT)"
            )
        )
        session.execute(
            sql_text("INSERT INTO account_profile_cache (id, uname, mid) VALUES (1, 'old_user', 42)")
        )
        meta.version = 2
        session.commit()

    init_db()  # 触发 v2→v3 迁移 + create_all 重建

    with session_scope() as session:
        meta = session.get(SchemaMeta, 1)
        assert int(meta.version) == SCHEMA_VERSION
        # 旧单例行已随表重建清除；新表按 uid 主键工作
        assert session.get(AccountProfileCacheRow, 1) is None
        session.add(AccountProfileCacheRow(uid=7, uname="u7", raw_json="{}"))
        session.add(AccountProfileCacheRow(uid=8, uname="u8", raw_json="{}"))
        session.commit()
        assert session.get(AccountProfileCacheRow, 7).uname == "u7"
        assert session.get(AccountProfileCacheRow, 8).uname == "u8"


def test_init_db_hard_fails_on_future_schema(isolated_home: Path) -> None:
    """核心不变量：未来版本 DB 在任何写操作之前 hard fail，绝不自动降级回写。"""
    init_db()
    with session_scope() as session:
        meta = session.get(SchemaMeta, 1)
        assert meta is not None
        meta.version = SCHEMA_VERSION + 1
        session.commit()
    with pytest.raises(RuntimeError):
        init_db()
    # 版本号必须保持原样，且 init_db 失败前未产生任何结构性写入
    with session_scope() as session:
        meta = session.get(SchemaMeta, 1)
        assert meta is not None
        assert int(meta.version) == SCHEMA_VERSION + 1


def test_init_db_meta_row_missing_with_business_table_fails_closed(isolated_home: Path) -> None:
    """#31：schema_meta 行缺失但存在业务表 → 拒绝启动（fail-closed），
    绝不把元数据损坏的旧库标记为最新版本。"""
    from sqlalchemy import text as sql_text

    init_db()
    with session_scope() as session:
        session.execute(sql_text("DELETE FROM schema_meta WHERE id=1"))
        session.commit()
    with pytest.raises(RuntimeError, match="元数据"):
        init_db()
    # 拒绝启动时版本行必须保持缺失（未被写回"最新版本"）
    with session_scope() as session:
        assert session.get(SchemaMeta, 1) is None


def test_init_db_meta_row_missing_fresh_db_initializes(isolated_home: Path) -> None:
    """#31：仅 schema_meta 空表（无业务表）→ 视为真全新库，正常补齐并建表。"""
    from sqlalchemy import text as sql_text

    from src.db.engine import db_path, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    if db_path().exists():
        db_path().unlink()
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(sql_text("CREATE TABLE schema_meta (id INTEGER PRIMARY KEY, version INTEGER)"))
    init_db()
    with session_scope() as session:
        meta = session.get(SchemaMeta, 1)
        assert meta is not None
        assert int(meta.version) == SCHEMA_VERSION
        # create_all 已补建全部业务表
        assert (
            session.execute(
                sql_text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='jobs'")
            ).fetchone()
            is not None
        )


def test_load_watch_sync_dict_fallback_users_failed_type(isolated_home: Path) -> None:
    """#24：raw_json 缺失走列 fallback 时，users_failed 必须保持 list 类型。"""
    from sqlalchemy import text as sql_text

    from src.db.snapshots import load_watch_sync_dict, save_watch_sync_dict

    save_watch_sync_dict(
        {
            "source_id": "WATCH",
            "synced_at": 1,
            "window_start": 1,
            "window_end": 2,
            "checked_at": 1,
            "activity_links": [],
            "link_count": 0,
            "users_total": 1,
            "users_ok": 0,
            "users_failed": [{"mid": 1, "name": "a", "message": "x"}],
            "user_results": [],
        }
    )
    # 清空 raw_json，强制走列 fallback 路径
    with session_scope() as session:
        session.execute(sql_text("UPDATE watch_sync_snapshots SET raw_json='' WHERE id=1"))
        session.commit()
    payload = load_watch_sync_dict()
    assert isinstance(payload["users_failed"], list)
    assert payload["users_failed"] == []
    assert payload["users_ok"] == 0
    assert payload["users_total"] == 1


def test_get_engine_thread_safe_singleton(isolated_home: Path) -> None:
    """#32：get_engine 全局 singleton 并发首次创建时返回同一实例、无竞态。"""
    import threading

    from src.db.engine import get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    engines: list = []
    errors: list = []

    def worker() -> None:
        try:
            engines.append(get_engine())
        except Exception as exc:  # noqa: BLE001 - 测试收集
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert len(engines) == 8
    assert all(e is engines[0] for e in engines)


def test_activity_codec_preserves_business_type_int(isolated_home: Path) -> None:
    _ = isolated_home
    item = {
        "dynamic_id": "1234567890123456789",
        "business_type": 10,
        "lottery_type": "互动抽奖",
        "prizes": [{"description": "奖", "winner_count": 1}],
    }
    row = activity_dict_to_row(item, updated_at=1)
    back = row_to_activity_dict(row)
    assert back["business_type"] == 10
    assert back["prizes"][0]["description"] == "奖"


def test_activity_crud_counts(isolated_home: Path) -> None:
    replace_all_activities(
        [
            {
                "dynamic_id": "1",
                "lottery_type": "转发抽奖",
                "draw_status": "active",
                "activity_status": "未参加",
            },
            {
                "dynamic_id": "2",
                "lottery_type": "互动抽奖",
                "draw_status": "ended",
                "activity_status": "已结束",
            },
        ]
    )
    assert activity_count() == 2
    assert {a["dynamic_id"] for a in load_activities()} == {"1", "2"}


def test_state_checkpoint_roundtrip(isolated_home: Path) -> None:
    save_state({"sources": {}})
    assert get_last_container("DS-2") is None
    set_last_container("DS-2", "https://example.com/cv1", container_id="cv1", title="t")
    assert get_last_container("DS-2") == "https://example.com/cv1"


def test_participation_roundtrip(isolated_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.db.uids.participation_uid", lambda: "test-uid")
    monkeypatch.setattr("src.participation_store.participation_uid", lambda: "test-uid")
    set_participation("111", "已参加")
    loaded = load_participations()
    assert loaded["111"].user_status == "已参加"


def _write_minimal_json_tree(home: Path) -> None:
    data = home / "data"
    config = home / "config"
    (data / "output").mkdir(parents=True, exist_ok=True)
    (data / "cache").mkdir(parents=True, exist_ok=True)
    (data / "users" / "1").mkdir(parents=True, exist_ok=True)
    config.mkdir(parents=True, exist_ok=True)

    (data / "output" / "activities_latest.json").write_text(
        json.dumps(
            {
                "updated_at": 1,
                "activities": [
                    {
                        "dynamic_id": "1000000000000000001",
                        "lottery_type": "互动抽奖",
                        "business_type": 10,
                        "draw_status": "active",
                        "activity_status": "未参加",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (data / "state.json").write_text(
        json.dumps(
            {
                "sources": {
                    "DS-1": {
                        "container_url": "https://example.com/a",
                        "container_id": "a",
                        "checked_at": 1,
                    }
                },
                "watch": {"last_synced_at": 2},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (config / "watch_users.json").write_text(
        json.dumps({"updated_at": 1, "users": [{"mid": 42, "name": "测试"}]}),
        encoding="utf-8",
    )
    (data / "users" / "1" / "participations.json").write_text(
        json.dumps(
            {
                "entries": {
                    "1000000000000000001": {
                        "dynamic_id": "1000000000000000001",
                        "user_status": "已参加",
                        "updated_at": 1,
                        "source": "participate",
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def test_import_json_dry_and_nonempty_guard(isolated_home: Path) -> None:
    _write_minimal_json_tree(isolated_home)
    report = run_import(force=True, yes=True, archive=False)
    assert any(line.kind == "activities" and line.imported == 1 for line in report.lines)
    assert activity_count() == 1
    assert get_last_container("DS-1") == "https://example.com/a"

    with pytest.raises(JsonImportError) as exc:
        run_import(force=False, yes=False, archive=False)
    assert exc.value.code == EXIT_NONEMPTY


def test_import_json_missing_required_fails(isolated_home: Path) -> None:
    # 仅建目录，不写 activities / state / watch_users
    (isolated_home / "data" / "output").mkdir(parents=True, exist_ok=True)
    with pytest.raises(JsonImportError) as exc:
        run_import(force=True, yes=True, archive=False)
    assert exc.value.code == EXIT_SOURCE


def test_import_json_archives_sources(isolated_home: Path) -> None:
    _write_minimal_json_tree(isolated_home)
    run_import(force=True, yes=True, archive=True)
    assert not (isolated_home / "data" / "output" / "activities_latest.json").exists()
    archived = (
        isolated_home / "data" / "backup" / "json_pre_sqlite" / "data" / "output" / "activities_latest.json"
    )
    assert archived.is_file()
    assert (isolated_home / "data" / "binggo.db").is_file()


def test_activity_codec_string_false_stays_false(isolated_home: Path) -> None:
    """迁移/导入数据里的字符串假值不得被 bool() 翻成 True。"""
    _ = isolated_home
    base = {
        "dynamic_id": "1234567890123456789",
        "lottery_type": "预约抽奖",
        "prizes": [{"description": "奖", "winner_count": 1}],
    }
    for raw in ("false", "False", "0", "", "no", "off", "null"):
        item = dict(base, skipped=raw, status_classified=raw, platform_participated=raw, reserve_reserved=raw)
        back = row_to_activity_dict(activity_dict_to_row(item, updated_at=1))
        assert back["skipped"] is False, raw
        assert back["status_classified"] is False, raw
        assert back["platform_participated"] is False, raw
        assert back["reserve_reserved"] is False, raw

    for raw in ("true", "1", "yes"):
        item = dict(base, skipped=raw)
        assert row_to_activity_dict(activity_dict_to_row(item, updated_at=1))["skipped"] is True, raw

    # None 仍表示"未知"，不能被压成 False
    item = dict(base, platform_participated=None)
    assert row_to_activity_dict(activity_dict_to_row(item, updated_at=1))["platform_participated"] is None
