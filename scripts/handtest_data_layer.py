#!/usr/bin/env python3
"""方向一手测清单自动化核对（开发机真实数据）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from src.app_paths import COOKIE_PATH, DATA_DIR, LLM_ENV_PATH, ensure_user_dirs
    from src.activity_store import activity_count, load_payload
    from src.db.engine import db_path, reset_engine_for_tests
    from src.db.schema import init_db
    from src.db.snapshots import load_ds_check_dict, load_watch_sync_dict
    from src.db.session import session_scope
    from src.db.models import (
        ForwardClassifyCacheRow,
        ForwardParseCacheRow,
        ParticipationActionRow,
        ParticipationRow,
        WatchUserRow,
    )
    from src.forward_parse_cache import load_cache as load_parse_cache
    from src.forward_classify_cache import load_cache as load_classify_cache
    from src.state_store import get_last_container, get_last_pipeline_persisted, load_state
    from src.watch_users import get_watch_users_payload, list_watch_users
    from sqlmodel import select
    from web.activity_service import get_summary, list_activities

    ensure_user_dirs()
    init_db()

    checks: list[tuple[str, bool, str]] = []

    def ok(name: str, cond: bool, detail: str = "") -> None:
        checks.append((name, cond, detail))

    db = db_path()
    ok("DB 文件存在", db.is_file(), str(db))

    payload = load_payload()
    n_act = len(payload.get("activities") or [])
    ok("活动条数>0", n_act > 0, f"count={n_act}")
    ok("activity_count 一致", activity_count() == n_act, f"{activity_count()} vs {n_act}")

    archive = DATA_DIR / "backup" / "json_pre_sqlite"
    archived = list(archive.rglob("*.json")) if archive.exists() else []
    ok("归档目录存在", archive.is_dir(), str(archive))
    ok("归档含 JSON", len(archived) >= 10, f"files={len(archived)}")
    ok(
        "运行时 activities JSON 已移走",
        not (DATA_DIR / "output" / "activities_latest.json").exists(),
    )
    ok("运行时 state.json 已移走", not (DATA_DIR / "state.json").exists())
    ok("cookies 仍在原处", COOKIE_PATH.exists(), str(COOKIE_PATH))
    # llm.env 可能尚未配置，存在或 example 即可
    ok(
        "llm 配置仍文件化",
        LLM_ENV_PATH.exists() or (LLM_ENV_PATH.parent / "llm.env.example").exists(),
        str(LLM_ENV_PATH),
    )

    state = load_state()
    ok("state.sources 非空", bool(state.get("sources")), f"keys={list((state.get('sources') or {}).keys())}")
    ok("DS-1 检查点可读", bool(get_last_container("DS-1")))

    watch = list_watch_users(ensure_seeded=False)
    ok("监控用户>0", len(watch) > 0, f"count={len(watch)}")
    wp = get_watch_users_payload(ensure_seeded=False)
    ok("监控 payload.count", int(wp.get("count") or 0) == len(watch))

    ds1 = load_ds_check_dict("DS-1")
    ok("DS-1 快照可读", ds1 is not None and bool(ds1.get("activity_links")))
    watch_snap = load_watch_sync_dict()
    ok("WATCH 快照可读", watch_snap is not None, f"links={watch_snap.get('link_count') if watch_snap else None}")

    parse_n = len(load_parse_cache())
    classify_n = len(load_classify_cache())
    ok("forward_parse 缓存", parse_n > 0, f"entries={parse_n}")
    ok("forward_classify 缓存", classify_n > 0, f"entries={classify_n}")

    with session_scope() as session:
        part_n = len(session.exec(select(ParticipationRow)).all())
        act_n = len(session.exec(select(ParticipationActionRow)).all())
        wu_n = len(session.exec(select(WatchUserRow)).all())
        fp_n = len(session.exec(select(ForwardParseCacheRow)).all())
        fc_n = len(session.exec(select(ForwardClassifyCacheRow)).all())
    ok("participations 行>0", part_n > 0, f"n={part_n}")
    ok("participation_actions 行>0", act_n > 0, f"n={act_n}")
    ok("watch_users 表一致", wu_n == len(watch), f"{wu_n} vs {len(watch)}")
    ok("parse cache 表一致", fp_n == parse_n, f"{fp_n} vs {parse_n}")
    ok("classify cache 表一致", fc_n == classify_n, f"{fc_n} vs {classify_n}")

    # 业务门面：概览 / 列表
    summary = get_summary()
    ok("概览 total_count", int(summary.get("total_count") or 0) > 0, str(summary.get("total_count")))
    ok(
        "概览 sources",
        isinstance(summary.get("sources"), list) and len(summary["sources"]) >= 6,
        f"n={len(summary.get('sources') or [])}",
    )
    listed = list_activities(page=1, page_size=20)
    items = listed.get("items") if isinstance(listed, dict) else None
    total = int((listed or {}).get("total") or 0) if isinstance(listed, dict) else 0
    ok(
        "活动列表分页",
        isinstance(listed, dict) and isinstance(items, list) and total >= 0,
        f"page={len(items or [])} total={total}",
    )

    # 重启进程语义：dispose engine 后重读
    before = activity_count()
    reset_engine_for_tests()
    init_db()
    after = activity_count()
    ok("重启引擎后数据仍在", before == after and after > 0, f"{before} -> {after}")

    pipeline = get_last_pipeline_persisted()
    ok("pipeline 可读", isinstance(pipeline, dict), json.dumps(pipeline, ensure_ascii=False))

    print("=== 方向一手测核对 ===")
    failed = 0
    for name, passed, detail in checks:
        mark = "PASS" if passed else "FAIL"
        if not passed:
            failed += 1
        print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))
    print(f"结果: {len(checks) - failed}/{len(checks)} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
