from __future__ import annotations

import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from src.app_logging import get_logger
from src.bilibili_login import LoginCancelledError
from src.writer_lock import WriterLock
from src.job_store import (
    finish_job,
    get_job,
    get_latest_job,
    insert_running_job,
    mark_interrupted_running,
    prune_old_jobs,
    truncate_log_summary,
    update_job_progress,
)
from src.log_context import job_log_context
from src.log_span import log_event
from web.actions import TripleParticipateFailed, run_action
from web.event_hub import event_hub
from web.user_messages import JOB_ACTION_LABELS, friendly_error, sanitize_log

logger = get_logger("job")


def _publish_job_event(event: str, data: dict[str, Any]) -> None:
    try:
        event_hub.publish(event, data)
    except Exception:
        logger.exception("发布任务事件失败 event=%s", event)

JobState = Literal["idle", "running", "success", "error", "cancelled", "interrupted"]
JobSource = Literal["ui", "auto", "system"]
ProgressCallback = Callable[..., None]
_PROGRESS_DB_INTERVAL_SEC = 1.0
# 内存日志上限（完整轨迹仍以 binggo.log 为准；入库另截 16KB）
_MEMORY_LOG_MAX_BYTES = 256 * 1024


@dataclass
class JobStatus:
    id: int | None = None
    state: JobState = "idle"
    action: str = ""
    label: str = ""
    source: str = "ui"
    started_at: int | None = None
    finished_at: int | None = None
    message: str = ""
    log: str = ""
    result: dict[str, Any] | None = None
    progress_step: int = 0
    progress_total: int = 0
    progress_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "state": self.state,
            "action": self.action,
            "label": self.label,
            "source": self.source,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "message": self.message,
            "log": self.log,
            "result": self.result,
            "progress_step": self.progress_step,
            "progress_total": self.progress_total,
            "progress_message": self.progress_message,
        }


def _is_cancel_exception(exc: BaseException) -> bool:
    """仅识别明确的取消异常文案，避免误伤「已取消关注」等业务错误。"""
    text = str(exc or "").strip()
    if not text:
        return False
    exact = {
        "任务已取消",
        "已取消扫码登录",
        "登录已取消",
        "用户取消",
        "用户已取消",
    }
    if text in exact:
        return True
    return text.startswith("任务已取消")


def _build_label(action: str, params: dict[str, Any]) -> str:
    label = JOB_ACTION_LABELS.get(action, action)
    if action == "participate" and params.get("dynamic_id"):
        label = f"{label} {params['dynamic_id']}"
    elif action == "refresh_source" and params.get("source_id"):
        label = f"{label} {params['source_id']}"
    return label


def _status_from_row(row: dict[str, Any]) -> JobStatus:
    state = str(row.get("state") or "idle")
    if state not in {"idle", "running", "success", "error", "cancelled", "interrupted"}:
        state = "error"
    return JobStatus(
        id=row.get("id"),
        state=state,  # type: ignore[arg-type]
        action=str(row.get("action") or ""),
        label=str(row.get("label") or ""),
        source=str(row.get("source") or "ui"),
        started_at=row.get("started_at"),
        finished_at=row.get("finished_at"),
        message=str(row.get("message") or ""),
        log=str(row.get("log_summary") or ""),
        result=row.get("result") if isinstance(row.get("result"), dict) else None,
        progress_step=int(row.get("progress_step") or 0),
        progress_total=int(row.get("progress_total") or 0),
        progress_message=str(row.get("message") or ""),
    )


def _copy_status(status: JobStatus) -> JobStatus:
    return JobStatus(
        id=status.id,
        state=status.state,
        action=status.action,
        label=status.label,
        source=status.source,
        started_at=status.started_at,
        finished_at=status.finished_at,
        message=status.message,
        log=status.log,
        result=dict(status.result) if isinstance(status.result, dict) else status.result,
        progress_step=status.progress_step,
        progress_total=status.progress_total,
        progress_message=status.progress_message,
    )


def _append_memory_log(current: str, chunk: str) -> str:
    if not chunk:
        return current
    merged = f"{current}\n{chunk}".strip() if current.strip() else chunk
    return truncate_log_summary(merged, max_bytes=_MEMORY_LOG_MAX_BYTES)


class JobRunner:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._status = JobStatus()
        self._cancel_event: threading.Event | None = None
        self._last_db_flush_at = 0.0
        self._recovered = False
        self._run_started_mono: float | None = None

    def recover_on_startup(self) -> None:
        """启动时：残留 running → interrupted；清理过期历史；加载最近快照。"""
        try:
            marked = mark_interrupted_running()
            pruned = prune_old_jobs()
            if marked or pruned:
                logger.info("任务恢复：interrupted=%s pruned=%s", marked, pruned)
        except Exception:
            logger.exception("任务恢复写库失败")
        latest = None
        try:
            latest = get_latest_job()
        except Exception:
            logger.exception("读取最近任务失败")
        with self._lock:
            if self._status.state == "running" and self._status.id is not None:
                # 已有进行中任务（极端：recover 被重复调用）则不覆盖
                self._recovered = True
                return
            if latest is not None and (
                self._status.state == "idle" and not self._status.action
            ):
                self._status = _status_from_row(latest)
            self._recovered = True

    def get_status(self) -> JobStatus:
        with self._lock:
            return _copy_status(self._status)

    def is_running(self) -> bool:
        with self._lock:
            return self._status.state == "running"

    def start(
        self,
        action: str,
        params: dict[str, Any] | None = None,
        *,
        source: JobSource | str = "ui",
    ) -> bool:
        return self.try_start(action, params, source=source) is not None

    def try_start(
        self,
        action: str,
        params: dict[str, Any] | None = None,
        *,
        source: JobSource | str = "ui",
    ) -> int | None:
        params = params or {}
        label = _build_label(action, params)
        now = int(time.time())
        source_s = str(source or "ui")

        # 跨进程写者锁：Web 单任务槽只管本进程，CLI（docs/cli.md 的正式入口）
        # 同样会写 B 站与本地状态。拿不到就当作"已有任务在跑"，与内存槽被占同义。
        writer_lock = WriterLock(owner=f"web:{action}")
        if not writer_lock.acquire():
            logger.warning("写者锁被本机其他进程持有，拒绝启动 action=%s", action)
            return None

        with self._lock:
            if self._status.state == "running":
                writer_lock.release()
                return None
            previous = _copy_status(self._status)
            self._cancel_event = threading.Event()
            self._last_db_flush_at = 0.0
            # 先占槽再写库，避免持锁做 IO；id 稍后回填
            self._status = JobStatus(
                id=None,
                state="running",
                action=action,
                label=label,
                source=source_s,
                started_at=now,
                message="任务已启动…",
            )

        try:
            job_id = insert_running_job(
                action=action,
                label=label,
                source=source_s,
                params=params,
                message="任务已启动…",
                now=now,
            )
        except Exception:
            writer_lock.release()
            logger.exception("创建任务行失败 action=%s", action)
            with self._lock:
                if (
                    self._status.state == "running"
                    and self._status.id is None
                    and self._status.action == action
                    and self._status.started_at == now
                ):
                    self._status = previous
                    self._cancel_event = None
            raise

        with self._lock:
            if self._status.state != "running" or self._status.action != action:
                # 占槽已被清掉：避免留下幽灵 running 行
                writer_lock.release()
                logger.error("任务占槽状态异常，放弃启动 action=%s job_id=%s", action, job_id)
                try:
                    finish_job(
                        job_id,
                        state="interrupted",
                        message="任务启动被中断",
                        log_summary="",
                        error_kind="interrupted",
                        finished_at=int(time.time()),
                    )
                except Exception:
                    logger.exception("清理异常启动任务失败 job_id=%s", job_id)
                return None
            self._status.id = job_id
            cancel_event = self._cancel_event

        _publish_job_event(
            "job.created",
            {
                "id": job_id,
                "state": "running",
                "action": action,
                "source": source_s,
                "label": label,
                "message": "任务已启动",
                "progress_step": 0,
                "progress_total": 0,
                "result": {},
            },
        )
        logger.info("任务启动 job_id=%s action=%s source=%s", job_id, action, source_s)
        thread = threading.Thread(
            target=self._run_worker,
            args=(job_id, action, params, cancel_event, writer_lock),
            daemon=True,
            name=f"job-{job_id}-{action}",
        )
        thread.start()
        return job_id

    def cancel(self) -> bool:
        with self._lock:
            if self._status.state != "running":
                return False
            if self._cancel_event:
                self._cancel_event.set()
            logger.info("任务取消请求 job_id=%s action=%s", self._status.id, self._status.action)
            return True

    def wait_until_terminal(
        self,
        job_id: int,
        *,
        timeout_sec: float,
        should_stop: Callable[[], bool] | None = None,
        poll_interval_sec: float = 2.0,
        initial_delay_sec: float = 0.8,
    ) -> JobStatus:
        """只读等待指定 job 离开 running；绝不 cancel。"""
        deadline = time.monotonic() + float(timeout_sec)
        if initial_delay_sec > 0:
            time.sleep(initial_delay_sec)
        last = self.resolve_job_status(job_id)
        while True:
            if should_stop and should_stop():
                return last
            status = self.resolve_job_status(job_id)
            last = status
            if status.state != "running":
                return status
            if time.monotonic() > deadline:
                raise TimeoutError(f"等待任务 #{job_id} 超时（超过 {int(timeout_sec)} 秒）")
            time.sleep(max(0.05, float(poll_interval_sec)))

    def resolve_job_status(self, job_id: int) -> JobStatus:
        current = self.get_status()
        if current.id == job_id:
            return current
        row = get_job(job_id)
        if row is not None:
            return _status_from_row(row)
        # 行已不存在：不要误用「当前其它任务」快照
        return JobStatus(
            id=job_id,
            state="interrupted",
            action=current.action if current.id == job_id else "",
            label=current.label if current.id == job_id else "",
            source=current.source if current.id == job_id else "system",
            message="任务记录已丢失",
            finished_at=int(time.time()),
        )

    def _make_progress_callback(self, job_id: int) -> ProgressCallback:
        def on_progress(
            *,
            step: int,
            total: int,
            message: str,
            log_append: str | None = None,
            qrcode_refreshed_at: int | None = None,
            login_phase: str | None = None,
            result_patch: dict[str, Any] | None = None,
        ) -> None:
            should_flush = False
            flush_payload: dict[str, Any] | None = None
            publish_progress = False
            progress_event: dict[str, Any] | None = None
            log_chunk: str | None = None
            with self._lock:
                if self._status.id != job_id or self._status.state != "running":
                    return
                prev_step = self._status.progress_step
                prev_message = self._status.message
                self._status.progress_step = step
                self._status.progress_total = total
                self._status.progress_message = message
                self._status.message = message
                cleaned_chunk = ""
                if log_append:
                    cleaned_chunk = sanitize_log(log_append) or ""
                    if cleaned_chunk:
                        self._status.log = _append_memory_log(self._status.log, cleaned_chunk)
                        log_chunk = cleaned_chunk
                result_delta: dict[str, Any] | None = None
                result_touch = (
                    qrcode_refreshed_at is not None
                    or login_phase is not None
                    or result_patch is not None
                )
                if result_touch:
                    merged = dict(self._status.result or {})
                    if qrcode_refreshed_at is not None:
                        merged["qrcode_refreshed_at"] = qrcode_refreshed_at
                    if login_phase is not None:
                        merged["login_phase"] = login_phase
                    if result_patch is not None:
                        merged.update(result_patch)
                    self._status.result = merged
                    result_delta = {}
                    if login_phase is not None:
                        result_delta["login_phase"] = merged["login_phase"]
                    if qrcode_refreshed_at is not None:
                        result_delta["qrcode_refreshed_at"] = merged["qrcode_refreshed_at"]
                    if result_patch is not None:
                        result_delta.update(result_patch)
                now_mono = time.monotonic()
                login_touch = qrcode_refreshed_at is not None or login_phase is not None
                due = (now_mono - self._last_db_flush_at) >= _PROGRESS_DB_INTERVAL_SEC
                changed = (
                    step != prev_step
                    or message != prev_message
                    or result_touch
                    or bool(cleaned_chunk)
                )
                if changed:
                    publish_progress = True
                    progress_event = {
                        "id": job_id,
                        "step": self._status.progress_step,
                        "total": self._status.progress_total,
                        "message": self._status.message,
                    }
                    if result_delta:
                        progress_event["result"] = result_delta
                if step != prev_step or result_touch or login_touch or due:
                    should_flush = True
                    flush_payload = {
                        "step": self._status.progress_step,
                        "total": self._status.progress_total,
                        "message": self._status.message,
                        "log": self._status.log,
                        "result": dict(self._status.result) if self._status.result else None,
                    }
            if publish_progress and progress_event is not None:
                _publish_job_event("job.progress", progress_event)
            if log_chunk:
                _publish_job_event("job.log", {"id": job_id, "chunk": log_chunk})
            if should_flush and flush_payload is not None:
                try:
                    update_job_progress(
                        job_id,
                        step=int(flush_payload["step"]),
                        total=int(flush_payload["total"]),
                        message=str(flush_payload["message"]),
                        log_summary=str(flush_payload["log"]),
                        result=flush_payload["result"],
                    )
                    with self._lock:
                        if self._status.id == job_id:
                            self._last_db_flush_at = time.monotonic()
                except Exception:
                    logger.exception("任务进度写库失败 job_id=%s", job_id)

        return on_progress

    def _apply_terminal(
        self,
        job_id: int,
        *,
        state: JobState,
        message: str,
        log: str,
        result: dict[str, Any] | None,
        error_kind: str | None,
        started_mono: float | None = None,
    ) -> None:
        finished_at = int(time.time())
        with self._lock:
            if self._status.id != job_id or self._status.state != "running":
                return
            progress_step = self._status.progress_step
            progress_total = self._status.progress_total
            action_name = self._status.action
            if progress_total:
                progress_step = progress_total

        db_ok = False
        try:
            db_ok = bool(
                finish_job(
                    job_id,
                    state=state,
                    message=message,
                    log_summary=log,
                    result=result,
                    error_kind=error_kind,
                    progress_step=progress_step,
                    progress_total=progress_total,
                    finished_at=finished_at,
                )
            )
        except Exception:
            logger.exception("任务终态写库失败 job_id=%s state=%s", job_id, state)

        if not db_ok:
            # 仅当库内仍为 running 时补救，避免覆盖其它终态
            try:
                row = get_job(job_id)
                if row is not None and row.get("state") == "running":
                    finish_job(
                        job_id,
                        state=state,
                        message=message,
                        log_summary=log,
                        result=result,
                        error_kind=error_kind,
                        progress_step=progress_step,
                        progress_total=progress_total,
                        finished_at=finished_at,
                    )
                    db_ok = True
            except Exception:
                logger.exception("任务终态回写补救失败 job_id=%s", job_id)

        if db_ok:
            try:
                prune_old_jobs()
            except Exception:
                logger.exception("清理历史任务失败 job_id=%s", job_id)

        duration_ms: int | None = None
        if started_mono is not None:
            duration_ms = max(0, int((time.perf_counter() - started_mono) * 1000))
        publish_terminal = False
        with self._lock:
            if self._run_started_mono is not None:
                if duration_ms is None:
                    duration_ms = max(0, int((time.perf_counter() - self._run_started_mono) * 1000))
                self._run_started_mono = None
            if self._status.id == job_id:
                self._status.state = state
                self._status.finished_at = finished_at
                self._status.message = message
                self._status.log = log
                self._status.result = result
                self._status.progress_step = progress_step
                self._status.progress_total = progress_total
                publish_terminal = True
        if publish_terminal:
            _publish_job_event(
                "job.terminal",
                {
                    "id": job_id,
                    "state": state,
                    "action": action_name,
                    "message": message,
                    "log": log,
                    "result": result,
                },
            )
        # 已通过「本 job 仍为 running」守卫：即使内存槽已被替换，仍写 job.end 便于轨迹对齐
        log_event(
            logger,
            f"任务结束 state={state} message={message}",
            event="job.end",
            component="job",
            duration_ms=duration_ms,
            error_kind=error_kind,
            state=state,
        )

    def _run_worker(
        self,
        job_id: int,
        action: str,
        params: dict[str, Any],
        cancel_event: threading.Event | None,
        writer_lock: WriterLock | None = None,
    ) -> None:
        try:
            self._run_worker_body(job_id, action, params, cancel_event)
        finally:
            if writer_lock is not None:
                writer_lock.release()

    def _run_worker_body(
        self,
        job_id: int,
        action: str,
        params: dict[str, Any],
        cancel_event: threading.Event | None,
    ) -> None:
        with self._lock:
            job_source = str(self._status.source or "ui")
            started_mono = time.perf_counter()
            self._run_started_mono = started_mono
        with job_log_context(job_id=job_id, action=action, job_source=job_source):
            log_event(
                logger,
                f"任务启动 action={action} source={job_source}",
                event="job.start",
                component="job",
            )
            on_progress = self._make_progress_callback(job_id)
            try:
                payload = run_action(
                    action,
                    params,
                    on_progress=on_progress,
                    cancel_event=cancel_event,
                )
                if not isinstance(payload, dict):
                    raise RuntimeError("run_action 返回值无效")

                action_ok = payload.get("ok")
                if action_ok is None and action in {"participate", "participate_triple"}:
                    action_ok = False
                cancelled_flag = bool(payload.get("cancelled"))
                if cancel_event and cancel_event.is_set() and (not action_ok or cancelled_flag):
                    message = str(payload.get("message") or "任务已取消")
                    log = sanitize_log(str(payload.get("log") or message)) or message
                    result = payload.get("result") if isinstance(payload.get("result"), dict) else None
                    self._apply_terminal(
                        job_id,
                        state="cancelled",
                        message=message,
                        log=log,
                        result=result,
                        error_kind="cancelled",
                        started_mono=started_mono,
                    )
                    return

                state: JobState = "success" if action_ok else "error"
                message = str(payload.get("message") or "完成")
                log = self.get_status().log
                if payload.get("log"):
                    final_log = sanitize_log(str(payload.get("log")))
                    if final_log:
                        log = final_log
                incoming = payload.get("result")
                current = self.get_status()
                if isinstance(incoming, dict):
                    merged = dict(current.result or {})
                    merged.update(incoming)
                    result = merged
                elif current.result is not None:
                    result = current.result
                else:
                    result = None
                self._apply_terminal(
                    job_id,
                    state=state,
                    message=message,
                    log=log,
                    result=result,
                    error_kind=None if state == "success" else "business",
                    started_mono=started_mono,
                )
            except LoginCancelledError:
                self._apply_terminal(
                    job_id,
                    state="cancelled",
                    message="已取消扫码登录",
                    log="登录流程已结束",
                    result=None,
                    error_kind="cancelled",
                    started_mono=started_mono,
                )
            except Exception as exc:
                if (cancel_event and cancel_event.is_set()) or _is_cancel_exception(exc):
                    cancel_msg = str(exc) if _is_cancel_exception(exc) else "任务已取消"
                    self._apply_terminal(
                        job_id,
                        state="cancelled",
                        message=cancel_msg,
                        log=sanitize_log(str(exc)) or cancel_msg,
                        result=None,
                        error_kind="cancelled",
                        started_mono=started_mono,
                    )
                    return
                logger.exception("任务失败 job_id=%s action=%s", job_id, action)
                result = None
                if action == "login":
                    current = self.get_status()
                    result = dict(current.result or {})
                    result["login_phase"] = "error"
                elif isinstance(exc, TripleParticipateFailed):
                    # 三连部分失败：保留已完成活动摘要（partial_failure 语义，
                    # 外部副作用不可回滚，UI 需要知道哪些活动实际完成了）
                    result = {
                        "partial_failure": True,
                        "failed_dynamic_id": exc.failed_dynamic_id,
                        "completed": exc.completed,
                    }
                # error_kind 区分业务部分失败与内部程序异常（避免污染内部错误统计）
                error_kind = "business_partial" if isinstance(exc, TripleParticipateFailed) else "internal"
                self._apply_terminal(
                    job_id,
                    state="error",
                    message=friendly_error(exc),
                    log=sanitize_log(traceback.format_exc()) or friendly_error(exc),
                    result=result,
                    error_kind=error_kind,
                    started_mono=started_mono,
                )


runner = JobRunner()
