"""只读解析旧 JSON 并写入 SQLite（供 scripts/import_json_to_db.py 使用）。

归档相对路径统一相对 USER_HOME：
  data/backup/json_pre_sqlite/<相对 USER_HOME 的路径>
"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from src.db.activity_codec import activity_dict_to_row
from src.db.engine import db_path, get_engine
from src.db.json_cols import dumps_json
from src.db.models import (
    AccountProfileCacheRow,
    ActivityRow,
    DrawReminderSnapshotRow,
    ForwardClassifyCacheRow,
    ForwardParseCacheRow,
    MessageWatchRow,
    ParticipationActionRow,
    ParticipationRow,
    PipelineMetaRow,
    SourceCheckpointRow,
    UserSettingsRow,
    WatchMetaRow,
    WatchUserRow,
    WatchUsersMetaRow,
)
from src.db.schema import init_db
from src.db.snapshots import FILENAME_TO_SOURCE, save_ds_check_dict, save_watch_sync_dict
from src.db.uids import GLOBAL_SETTINGS_UID, LEGACY_PARTICIPATION_UID

EXIT_OK = 0
EXIT_NONEMPTY = 2
EXIT_SOURCE = 3
EXIT_DB = 4


def _user_home() -> Path:
    from src.app_paths import user_home

    return user_home()


def _data_dir() -> Path:
    return _user_home() / "data"


def _config_dir() -> Path:
    return _user_home() / "config"


def _archive_root() -> Path:
    return _data_dir() / "backup" / "json_pre_sqlite"


def _activities_path() -> Path:
    return _data_dir() / "output" / "activities_latest.json"


def _state_path() -> Path:
    return _data_dir() / "state.json"


def _watch_users_path() -> Path:
    return _config_dir() / "watch_users.json"


def _watch_candidates_path() -> Path:
    return _config_dir() / "watch_users_candidates.json"


def _global_settings_path() -> Path:
    return _config_dir() / "participate_settings.json"


def _account_cache_path() -> Path:
    return _data_dir() / "cache" / "account_profile.json"


def _forward_parse_path() -> Path:
    return _data_dir() / "cache" / "forward_parse_cache.json"


def _forward_classify_path() -> Path:
    return _data_dir() / "cache" / "forward_classify_cache.json"


def _ds_paths() -> dict[str, Path]:
    out = _data_dir() / "output"
    return {
        "DS-1": out / "ds1_latest.json",
        "DS-2": out / "ds2_latest.json",
        "DS-3": out / "ds3_latest.json",
        "DS-4": out / "ds4_latest.json",
        "DS-5": out / "ds5_latest.json",
        "DS-6": out / "ds6_latest.json",
        "DS-7": out / "ds7_latest.json",
    }


def _watch_latest_path() -> Path:
    return _data_dir() / "output" / "watch_latest.json"


def _users_dir() -> Path:
    return _data_dir() / "users"


def _legacy_participations() -> Path:
    return _data_dir() / "participations.json"


def _legacy_actions() -> Path:
    return _data_dir() / "participation_actions.json"


def __getattr__(name: str):
    if name == "ARCHIVE_ROOT":
        return _archive_root()
    raise AttributeError(name)


@dataclass
class LineReport:
    kind: str
    path: str
    status: str
    expected: int = 0
    imported: int = 0
    detail: str = ""


@dataclass
class ImportReport:
    lines: list[LineReport] = field(default_factory=list)
    archived: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add(self, line: LineReport) -> None:
        self.lines.append(line)
        if line.status == "error":
            self.errors.append(f"{line.kind}: {line.path}: {line.detail}")

    def print_summary(self) -> None:
        print("=== import_json_to_db 报告 ===")
        for line in self.lines:
            print(
                f"[{line.status}] {line.kind} {line.path} "
                f"expected={line.expected} imported={line.imported}"
                + (f" ({line.detail})" if line.detail else "")
            )
        if self.archived:
            print(f"已归档 {len(self.archived)} 个文件 → {_archive_root()}")
        if self.errors:
            print(f"错误 {len(self.errors)} 条")


class ImportError(RuntimeError):
    def __init__(self, message: str, code: int = EXIT_SOURCE) -> None:
        super().__init__(message)
        self.code = code


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(_user_home().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ImportError(f"JSON 损坏: {path}: {exc}", EXIT_SOURCE) from exc
    except OSError as exc:
        raise ImportError(f"无法读取: {path}: {exc}", EXIT_SOURCE) from exc


def _ensure_data_dirs() -> None:
    _data_dir().mkdir(parents=True, exist_ok=True)
    _config_dir().mkdir(parents=True, exist_ok=True)
    (_data_dir() / "output").mkdir(parents=True, exist_ok=True)
    (_data_dir() / "cache").mkdir(parents=True, exist_ok=True)
    (_data_dir() / "logs").mkdir(parents=True, exist_ok=True)


def _count_business_rows(session: Session) -> dict[str, int]:
    return {
        "activities": len(session.exec(select(ActivityRow.dynamic_id)).all()),
        "participations": len(session.exec(select(ParticipationRow.dynamic_id)).all()),
        "participation_actions": len(session.exec(select(ParticipationActionRow.id)).all()),
        "source_checkpoints": len(session.exec(select(SourceCheckpointRow.source_id)).all()),
        "watch_users": len(session.exec(select(WatchUserRow.mid)).all()),
        "user_settings": len(session.exec(select(UserSettingsRow.uid)).all()),
    }


def db_is_nonempty() -> bool:
    engine = get_engine()
    with Session(engine) as session:
        counts = _count_business_rows(session)
    return any(v > 0 for v in counts.values())


def _archive_file(path: Path, report: ImportReport) -> None:
    if not path.exists():
        return
    rel = _rel(path)
    dest = _archive_root() / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    src_hash = _sha256(path)
    src_size = path.stat().st_size
    shutil.copy2(path, dest)
    if dest.stat().st_size != src_size or _sha256(dest) != src_hash:
        raise ImportError(f"归档校验失败: {path} → {dest}", EXIT_SOURCE)
    path.unlink()
    report.archived.append(rel)


def _upsert_activity(session: Session, item: dict[str, Any], updated_at: int) -> None:
    dynamic_id = str(item.get("dynamic_id") or "").strip()
    if not dynamic_id:
        return
    row = activity_dict_to_row(item, updated_at=updated_at)
    existing = session.get(ActivityRow, dynamic_id)
    if existing is None:
        session.add(row)
    else:
        for name in ActivityRow.model_fields:
            if name == "dynamic_id":
                continue
            setattr(existing, name, getattr(row, name))


def _import_activities(session: Session, report: ImportReport) -> Path:
    path = _activities_path()
    if not path.exists():
        report.add(
            LineReport("activities", _rel(path), "error", detail="文件不存在（必需）")
        )
        raise ImportError(f"缺少必需文件: {path}", EXIT_SOURCE)
    payload = _read_json(path)
    if not isinstance(payload, dict):
        raise ImportError(f"activities 根节点须为对象: {path}", EXIT_SOURCE)
    items = [x for x in (payload.get("activities") or []) if isinstance(x, dict)]
    expected_ids = {
        str(item.get("dynamic_id") or "").strip()
        for item in items
        if str(item.get("dynamic_id") or "").strip()
    }
    expected = len(expected_ids)
    updated_at = int(payload.get("updated_at") or time.time())
    for item in items:
        _upsert_activity(session, item, updated_at)
    session.flush()
    missing = [did for did in expected_ids if session.get(ActivityRow, did) is None]
    if missing:
        raise ImportError(
            f"activities 校验失败: 缺少 {len(missing)} 条，例 {missing[:3]}",
            EXIT_SOURCE,
        )
    report.add(LineReport("activities", _rel(path), "ok", expected=expected, imported=expected))
    return path


def _import_state(session: Session, report: ImportReport) -> Path:
    path = _state_path()
    if not path.exists():
        report.add(LineReport("state", _rel(path), "error", detail="文件不存在（必需）"))
        raise ImportError(f"缺少必需文件: {path}", EXIT_SOURCE)
    payload = _read_json(path)
    if not isinstance(payload, dict):
        raise ImportError(f"state 根节点须为对象: {path}", EXIT_SOURCE)
    sources = payload.get("sources") or {}
    if not isinstance(sources, dict):
        raise ImportError("state.sources 须为对象", EXIT_SOURCE)
    for source_id, raw in sources.items():
        if not isinstance(raw, dict):
            continue
        sid = str(source_id)
        entry = SourceCheckpointRow(
            source_id=sid,
            container_url=raw.get("container_url"),
            container_id=raw.get("container_id"),
            title=raw.get("title"),
            cv_id=str(raw["cv_id"]) if raw.get("cv_id") is not None else None,
            checked_at=int(raw["checked_at"]) if raw.get("checked_at") is not None else None,
        )
        existing = session.get(SourceCheckpointRow, sid)
        if existing is None:
            session.add(entry)
        else:
            existing.container_url = entry.container_url
            existing.container_id = entry.container_id
            existing.title = entry.title
            existing.cv_id = entry.cv_id
            existing.checked_at = entry.checked_at
    watch = payload.get("watch") or {}
    if isinstance(watch, dict) and watch.get("last_synced_at") is not None:
        watch_row = session.get(WatchMetaRow, 1)
        if watch_row is None:
            session.add(WatchMetaRow(id=1, last_synced_at=int(watch["last_synced_at"])))
        else:
            watch_row.last_synced_at = int(watch["last_synced_at"])
    pipeline = payload.get("pipeline") or {}
    if isinstance(pipeline, dict):
        pipe_row = session.get(PipelineMetaRow, 1)
        if pipe_row is None:
            session.add(
                PipelineMetaRow(
                    id=1,
                    last_action=pipeline.get("last_action"),
                    last_persisted_count=int(pipeline.get("last_persisted_count") or 0),
                    last_synced_at=int(pipeline["last_synced_at"])
                    if pipeline.get("last_synced_at") is not None
                    else None,
                )
            )
        else:
            pipe_row.last_action = pipeline.get("last_action")
            pipe_row.last_persisted_count = int(pipeline.get("last_persisted_count") or 0)
            pipe_row.last_synced_at = (
                int(pipeline["last_synced_at"])
                if pipeline.get("last_synced_at") is not None
                else None
            )
    session.flush()
    count = len(sources)
    report.add(LineReport("state", _rel(path), "ok", expected=count, imported=count))
    return path


def _import_watch_users(session: Session, report: ImportReport) -> list[Path]:
    path = _watch_users_path()
    source_path = path if path.exists() else None
    if source_path is None and _watch_candidates_path().exists():
        source_path = _watch_candidates_path()
    if source_path is None:
        report.add(
            LineReport(
                "watch_users",
                _rel(path),
                "error",
                detail="watch_users.json 与 candidates 均不存在",
            )
        )
        raise ImportError("缺少 watch_users 源文件", EXIT_SOURCE)
    payload = _read_json(source_path)
    if not isinstance(payload, dict):
        raise ImportError(f"watch_users 根节点须为对象: {source_path}", EXIT_SOURCE)
    users = [u for u in (payload.get("users") or []) if isinstance(u, dict)]
    updated_at = int(payload.get("updated_at") or time.time())
    seeded_from = payload.get("seeded_from")
    seen: set[int] = set()
    for item in users:
        try:
            mid = int(item.get("mid") or 0)
        except (TypeError, ValueError):
            continue
        if mid <= 0 or mid in seen:
            continue
        seen.add(mid)
        name = str(item.get("name") or mid).strip() or str(mid)
        existing = session.get(WatchUserRow, mid)
        if existing is None:
            session.add(WatchUserRow(mid=mid, name=name, updated_at=updated_at))
        else:
            existing.name = name
            existing.updated_at = updated_at
    meta = session.get(WatchUsersMetaRow, 1)
    if meta is None:
        session.add(
            WatchUsersMetaRow(
                id=1,
                updated_at=updated_at,
                seeded_from=str(seeded_from) if seeded_from else source_path.name,
            )
        )
    else:
        meta.updated_at = updated_at
        meta.seeded_from = str(seeded_from) if seeded_from else source_path.name
    session.flush()
    imported = len(session.exec(select(WatchUserRow.mid)).all())
    expected = len(seen)
    if imported < expected:
        raise ImportError(f"watch_users 校验失败: {expected} vs {imported}", EXIT_SOURCE)
    report.add(
        LineReport(
            "watch_users",
            _rel(source_path),
            "ok",
            expected=expected,
            imported=imported,
            detail="from candidates" if source_path == _watch_candidates_path() else "",
        )
    )
    # candidates 永不归档；仅归档正式 watch_users.json
    to_archive: list[Path] = []
    if path.exists() and source_path == path:
        to_archive.append(path)
    elif path.exists():
        to_archive.append(path)
    return to_archive


def _iter_user_json_files(filename: str) -> list[tuple[str, Path]]:
    found: list[tuple[str, Path]] = []
    if _users_dir().is_dir():
        for child in sorted(_users_dir().iterdir()):
            if not child.is_dir():
                continue
            path = child / filename
            if path.exists():
                found.append((child.name, path))
    return found


def _import_participations(session: Session, report: ImportReport) -> list[Path]:
    scanned: list[tuple[str, Path]] = _iter_user_json_files("participations.json")
    if _legacy_participations().exists():
        scanned.append((LEGACY_PARTICIPATION_UID, _legacy_participations()))
    if not scanned:
        report.add(
            LineReport(
                "participations",
                "data/users/*/participations.json",
                "skip",
                detail="未找到任何参与文件（允许 0 条）",
            )
        )
        return []

    archived: list[Path] = []
    for uid, path in scanned:
        try:
            payload = _read_json(path)
        except ImportError:
            report.add(
                LineReport("participations", _rel(path), "error", detail="读取失败")
            )
            raise
        if not isinstance(payload, dict):
            raise ImportError(f"participations 根节点须为对象: {path}", EXIT_SOURCE)
        entries = payload.get("entries") or {}
        items: list[dict[str, Any]] = []
        if isinstance(entries, dict):
            items = [v for v in entries.values() if isinstance(v, dict)]
        elif isinstance(entries, list):
            items = [v for v in entries if isinstance(v, dict)]
        expected = 0
        for item in items:
            dynamic_id = str(item.get("dynamic_id") or "").strip()
            status = str(item.get("user_status") or "").strip()
            if not dynamic_id or status not in ("已参加", "未参加"):
                continue
            expected += 1
            updated_at = int(item.get("updated_at") or 0)
            source = str(item.get("source") or "") or None
            existing = session.get(ParticipationRow, (uid, dynamic_id))
            if existing is None:
                session.add(
                    ParticipationRow(
                        uid=uid,
                        dynamic_id=dynamic_id,
                        user_status=status,
                        updated_at=updated_at,
                        source=source,
                    )
                )
            else:
                existing.user_status = status
                existing.updated_at = updated_at
                existing.source = source
        session.flush()
        db_for_uid = len(
            session.exec(select(ParticipationRow).where(ParticipationRow.uid == uid)).all()
        )
        if db_for_uid < expected:
            raise ImportError(
                f"participations 校验失败 uid={uid}: JSON={expected} DB={db_for_uid}",
                EXIT_SOURCE,
            )
        report.add(
            LineReport(
                "participations",
                _rel(path),
                "ok",
                expected=expected,
                imported=expected,
                detail=f"uid={uid}; db_uid_total={db_for_uid}",
            )
        )
        archived.append(path)
    return archived


def _import_actions(session: Session, report: ImportReport) -> list[Path]:
    scanned: list[tuple[str, Path]] = _iter_user_json_files("participation_actions.json")
    if _legacy_actions().exists():
        scanned.append((LEGACY_PARTICIPATION_UID, _legacy_actions()))
    if not scanned:
        report.add(
            LineReport(
                "participation_actions",
                "data/users/*/participation_actions.json",
                "skip",
                detail="未找到任何动作日志（允许 0 条）",
            )
        )
        return []

    archived: list[Path] = []
    for uid, path in scanned:
        payload = _read_json(path)
        if not isinstance(payload, dict):
            raise ImportError(f"actions 根节点须为对象: {path}", EXIT_SOURCE)
        entries = payload.get("entries") or []
        if not isinstance(entries, list):
            raise ImportError(f"actions.entries 须为数组: {path}", EXIT_SOURCE)
        # 再导入：按 uid 删除再批量插入，避免重复日志
        old_rows = session.exec(
            select(ParticipationActionRow).where(ParticipationActionRow.uid == uid)
        ).all()
        for row in old_rows:
            session.delete(row)
        session.flush()
        expected = 0
        for item in entries:
            if not isinstance(item, dict):
                continue
            expected += 1
            session.add(
                ParticipationActionRow(
                    uid=uid,
                    recorded_at=int(item.get("recorded_at") or 0),
                    dynamic_id=str(item.get("dynamic_id") or ""),
                    lottery_type=str(item.get("lottery_type") or ""),
                    status=str(item.get("status") or ""),
                    message=str(item.get("message") or ""),
                    action_text=str(item.get("action_text") or ""),
                    actions_json=dumps_json(item.get("actions") or []),
                    context_snapshot_json=dumps_json(item.get("context_snapshot") or {}),
                )
            )
        session.flush()
        imported = len(
            session.exec(
                select(ParticipationActionRow).where(ParticipationActionRow.uid == uid)
            ).all()
        )
        if imported != expected:
            raise ImportError(
                f"actions 校验失败 uid={uid}: {expected} vs {imported}", EXIT_SOURCE
            )
        report.add(
            LineReport(
                "participation_actions",
                _rel(path),
                "ok",
                expected=expected,
                imported=imported,
                detail=f"uid={uid}; replace-by-uid",
            )
        )
        archived.append(path)
    return archived


def _upsert_settings(
    session: Session, uid: str, data: dict[str, Any], updated_at: int | None = None
) -> None:
    now = int(updated_at if updated_at is not None else time.time())
    row = session.get(UserSettingsRow, uid)
    if row is None:
        row = UserSettingsRow(uid=uid, updated_at=now)
        session.add(row)
    if "participate_text" in data:
        row.participate_text = data.get("participate_text")
    if "participate_fallback_text" in data:
        row.participate_fallback_text = data.get("participate_fallback_text")
    if "participate_text_mode" in data:
        row.participate_text_mode = data.get("participate_text_mode")
    row.updated_at = now


def _import_settings(session: Session, report: ImportReport) -> list[Path]:
    archived: list[Path] = []
    if _global_settings_path().exists():
        payload = _read_json(_global_settings_path())
        if not isinstance(payload, dict):
            raise ImportError("participate_settings.json 须为对象", EXIT_SOURCE)
        _upsert_settings(session, GLOBAL_SETTINGS_UID, payload)
        report.add(
            LineReport(
                "user_settings",
                _rel(_global_settings_path()),
                "ok",
                expected=1,
                imported=1,
                detail=f"uid={GLOBAL_SETTINGS_UID}",
            )
        )
        archived.append(_global_settings_path())
    else:
        report.add(
            LineReport(
                "user_settings",
                _rel(_global_settings_path()),
                "skip",
                detail="文件不存在（允许）",
            )
        )

    for uid, path in _iter_user_json_files("settings.json"):
        payload = _read_json(path)
        if not isinstance(payload, dict):
            raise ImportError(f"settings 须为对象: {path}", EXIT_SOURCE)
        _upsert_settings(session, uid, payload, updated_at=payload.get("updated_at"))
        report.add(
            LineReport(
                "user_settings",
                _rel(path),
                "ok",
                expected=1,
                imported=1,
                detail=f"uid={uid}",
            )
        )
        archived.append(path)
    if not archived and not _global_settings_path().exists():
        report.add(
            LineReport(
                "user_settings",
                "data/users/*/settings.json",
                "skip",
                detail="未扫描到用户 settings",
            )
        )
    return archived


def _import_forward_cache(
    session: Session,
    path: Path,
    *,
    kind: str,
    model,
    report: ImportReport,
) -> Path | None:
    if not path.exists():
        report.add(LineReport(kind, _rel(path), "skip", detail="文件不存在"))
        return None
    payload = _read_json(path)
    if not isinstance(payload, dict):
        raise ImportError(f"{kind} 须为对象: {path}", EXIT_SOURCE)
    entries = payload.get("entries") or {}
    if not isinstance(entries, dict):
        raise ImportError(f"{kind}.entries 须为对象: {path}", EXIT_SOURCE)
    now = int(time.time())
    expected = 0
    for dynamic_id, entry in entries.items():
        if not isinstance(entry, dict):
            continue
        did = str(dynamic_id)
        expected += 1
        existing = session.get(model, did)
        content_hash = str(entry.get("content_hash") or "")
        parsed_json = dumps_json(entry.get("parsed") or {})
        if existing is None:
            session.add(
                model(
                    dynamic_id=did,
                    content_hash=content_hash,
                    parsed_json=parsed_json,
                    updated_at=now,
                )
            )
        else:
            existing.content_hash = content_hash
            existing.parsed_json = parsed_json
            existing.updated_at = now
    session.flush()
    missing = [
        did
        for did, entry in entries.items()
        if isinstance(entry, dict) and session.get(model, str(did)) is None
    ]
    if missing:
        raise ImportError(f"{kind} 校验失败: 缺少 {len(missing)} 条", EXIT_SOURCE)
    report.add(LineReport(kind, _rel(path), "ok", expected=expected, imported=expected))
    return path


def _import_account_cache(session: Session, report: ImportReport) -> Path | None:
    path = _account_cache_path()
    if not path.exists():
        report.add(LineReport("account_profile_cache", _rel(path), "skip", detail="文件不存在"))
        return None
    payload = _read_json(path)
    if not isinstance(payload, dict):
        raise ImportError("account_profile.json 须为对象", EXIT_SOURCE)
    now = int(time.time())
    row = session.get(AccountProfileCacheRow, 1)
    mid = payload.get("mid")
    following = payload.get("following")
    dynamic_count = payload.get("dynamic_count")
    data = AccountProfileCacheRow(
        id=1,
        uname=payload.get("uname"),
        face=payload.get("face"),
        mid=int(mid) if mid is not None else None,
        following=int(following) if following is not None else None,
        dynamic_count=int(dynamic_count) if dynamic_count is not None else None,
        updated_at=now,
        raw_json=dumps_json(payload),
    )
    if row is None:
        session.add(data)
    else:
        for name in (
            "uname",
            "face",
            "mid",
            "following",
            "dynamic_count",
            "updated_at",
            "raw_json",
        ):
            setattr(row, name, getattr(data, name))
    report.add(LineReport("account_profile_cache", _rel(path), "ok", expected=1, imported=1))
    return path


def _import_message_watch(session: Session, report: ImportReport) -> list[Path]:
    archived: list[Path] = []
    for uid_str, path in _iter_user_json_files("message_watch.json"):
        payload = _read_json(path)
        if not isinstance(payload, dict):
            raise ImportError(f"message_watch 须为对象: {path}", EXIT_SOURCE)
        try:
            uid = int(uid_str)
        except ValueError as exc:
            raise ImportError(f"非法 uid 目录: {uid_str}", EXIT_SOURCE) from exc
        last_seen = payload.get("last_seen_unread_at")
        updated_at = int(payload.get("updated_at") or time.time())
        row = session.get(MessageWatchRow, uid)
        if row is None:
            session.add(
                MessageWatchRow(
                    uid=uid,
                    last_seen_unread_at=int(last_seen) if last_seen is not None else None,
                    updated_at=updated_at,
                )
            )
        else:
            row.last_seen_unread_at = int(last_seen) if last_seen is not None else None
            row.updated_at = updated_at
        report.add(
            LineReport("message_watch", _rel(path), "ok", expected=1, imported=1, detail=f"uid={uid}")
        )
        archived.append(path)
    if not archived:
        report.add(
            LineReport(
                "message_watch",
                "data/users/*/message_watch.json",
                "skip",
                detail="未找到",
            )
        )
    return archived


def _import_draw_reminder(session: Session, report: ImportReport) -> list[Path]:
    archived: list[Path] = []
    for uid_str, path in _iter_user_json_files("draw_reminder.json"):
        payload = _read_json(path)
        if not isinstance(payload, dict):
            raise ImportError(f"draw_reminder 须为对象: {path}", EXIT_SOURCE)
        try:
            uid = int(uid_str)
        except ValueError as exc:
            raise ImportError(f"非法 uid 目录: {uid_str}", EXIT_SOURCE) from exc
        drawing_soon = payload.get("drawing_soon") or []
        if not isinstance(drawing_soon, list):
            drawing_soon = []
        count = int(payload.get("drawing_soon_count") or len(drawing_soon))
        updated_at = int(payload.get("updated_at") or time.time())
        row = session.get(DrawReminderSnapshotRow, uid)
        if row is None:
            session.add(
                DrawReminderSnapshotRow(
                    uid=uid,
                    drawing_soon_count=count,
                    drawing_soon_json=dumps_json(drawing_soon),
                    at_notify_url=payload.get("at_notify_url"),
                    updated_at=updated_at,
                )
            )
        else:
            row.drawing_soon_count = count
            row.drawing_soon_json = dumps_json(drawing_soon)
            row.at_notify_url = payload.get("at_notify_url")
            row.updated_at = updated_at
        report.add(
            LineReport(
                "draw_reminder",
                _rel(path),
                "ok",
                expected=1,
                imported=1,
                detail=f"uid={uid}",
            )
        )
        archived.append(path)
    if not archived:
        report.add(
            LineReport(
                "draw_reminder",
                "data/users/*/draw_reminder.json",
                "skip",
                detail="未找到",
            )
        )
    return archived


def _import_ds_and_watch(report: ImportReport) -> list[Path]:
    """DS/WATCH 快照经 snapshots 模块写入（独立短事务）。"""
    archived: list[Path] = []
    for source_id, path in _ds_paths().items():
        if not path.exists():
            report.add(LineReport("ds_check_snapshots", _rel(path), "skip", detail="文件不存在"))
            continue
        payload = _read_json(path)
        if not isinstance(payload, dict):
            raise ImportError(f"ds 快照须为对象: {path}", EXIT_SOURCE)
        if not payload.get("source_id"):
            payload["source_id"] = source_id
        save_ds_check_dict(payload)
        links = payload.get("activity_links") or []
        count = len(links) if isinstance(links, list) else 0
        report.add(
            LineReport(
                "ds_check_snapshots",
                _rel(path),
                "ok",
                expected=count,
                imported=count,
                detail=source_id,
            )
        )
        archived.append(path)

    path = _watch_latest_path()
    if not path.exists():
        report.add(LineReport("watch_sync_snapshots", _rel(path), "skip", detail="文件不存在"))
    else:
        payload = _read_json(path)
        if not isinstance(payload, dict):
            raise ImportError(f"watch 快照须为对象: {path}", EXIT_SOURCE)
        save_watch_sync_dict(payload)
        links = payload.get("activity_links") or []
        count = len(links) if isinstance(links, list) else 0
        report.add(
            LineReport("watch_sync_snapshots", _rel(path), "ok", expected=count, imported=count)
        )
        archived.append(path)
    return archived


def run_import(*, force: bool = False, yes: bool = False, archive: bool = True) -> ImportReport:
    """执行全量导入。成功返回报告；失败抛 ImportError。"""
    report = ImportReport()
    _ensure_data_dirs()
    init_db()

    if db_is_nonempty() and not force:
        if not yes:
            raise ImportError(
                "数据库非空。确认 upsert 覆盖请传 --force，或交互确认。",
                EXIT_NONEMPTY,
            )

    engine = get_engine()
    to_archive: list[Path] = []
    try:
        with Session(engine) as session:
            try:
                to_archive.append(_import_activities(session, report))
                to_archive.append(_import_state(session, report))
                to_archive.extend(_import_watch_users(session, report))
                to_archive.extend(_import_participations(session, report))
                to_archive.extend(_import_actions(session, report))
                to_archive.extend(_import_settings(session, report))
                p = _import_forward_cache(
                    session,
                    _forward_parse_path(),
                    kind="forward_parse_cache",
                    model=ForwardParseCacheRow,
                    report=report,
                )
                if p:
                    to_archive.append(p)
                p = _import_forward_cache(
                    session,
                    _forward_classify_path(),
                    kind="forward_classify_cache",
                    model=ForwardClassifyCacheRow,
                    report=report,
                )
                if p:
                    to_archive.append(p)
                p = _import_account_cache(session, report)
                if p:
                    to_archive.append(p)
                to_archive.extend(_import_message_watch(session, report))
                to_archive.extend(_import_draw_reminder(session, report))
                session.commit()
            except Exception:
                session.rollback()
                raise
    except ImportError:
        raise
    except Exception as exc:
        raise ImportError(f"数据库写入失败: {exc}", EXIT_DB) from exc

    # DS/WATCH 使用独立 session（save_*_dict）
    try:
        to_archive.extend(_import_ds_and_watch(report))
    except ImportError:
        raise
    except Exception as exc:
        raise ImportError(f"快照写入失败: {exc}", EXIT_DB) from exc

    if any(line.status == "error" for line in report.lines):
        raise ImportError("导入过程存在错误行", EXIT_SOURCE)

    if archive:
        # 去重并保持顺序
        seen: set[str] = set()
        unique_paths: list[Path] = []
        for path in to_archive:
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            unique_paths.append(path)
        for path in unique_paths:
            # candidates 永不归档
            if path.resolve() == _watch_candidates_path().resolve():
                continue
            _archive_file(path, report)

    print(f"数据库: {db_path()}")
    report.print_summary()
    return report


# 供测试引用
__all__ = [
    "ARCHIVE_ROOT",
    "EXIT_DB",
    "EXIT_NONEMPTY",
    "EXIT_OK",
    "EXIT_SOURCE",
    "ImportError",
    "ImportReport",
    "db_is_nonempty",
    "run_import",
    "FILENAME_TO_SOURCE",
]
