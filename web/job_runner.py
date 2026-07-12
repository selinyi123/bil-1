from __future__ import annotations

import threading
import time
import traceback
from dataclasses import dataclass
from typing import Any, Callable, Literal

from src.bilibili_login import LoginCancelledError
from web.actions import run_action
from web.user_messages import JOB_ACTION_LABELS, friendly_error, sanitize_log

JobState = Literal["idle", "running", "success", "error"]
ProgressCallback = Callable[..., None]


@dataclass
class JobStatus:
    state: JobState = "idle"
    action: str = ""
    label: str = ""
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
            "state": self.state,
            "action": self.action,
            "label": self.label,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "message": self.message,
            "log": self.log,
            "result": self.result,
            "progress_step": self.progress_step,
            "progress_total": self.progress_total,
            "progress_message": self.progress_message,
        }


class JobRunner:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._status = JobStatus()
        self._cancel_event: threading.Event | None = None

    def get_status(self) -> JobStatus:
        with self._lock:
            return JobStatus(
                state=self._status.state,
                action=self._status.action,
                label=self._status.label,
                started_at=self._status.started_at,
                finished_at=self._status.finished_at,
                message=self._status.message,
                log=self._status.log,
                result=self._status.result,
                progress_step=self._status.progress_step,
                progress_total=self._status.progress_total,
                progress_message=self._status.progress_message,
            )

    def is_running(self) -> bool:
        with self._lock:
            return self._status.state == "running"

    def start(self, action: str, params: dict[str, Any] | None = None) -> bool:
        params = params or {}
        with self._lock:
            if self._status.state == "running":
                return False
            label = JOB_ACTION_LABELS.get(action, action)
            if action == "participate" and params.get("dynamic_id"):
                label = f"{label} {params['dynamic_id']}"

            self._cancel_event = threading.Event()
            self._status = JobStatus(
                state="running",
                action=action,
                label=label,
                started_at=int(time.time()),
                message="任务已启动…",
            )

        thread = threading.Thread(
            target=self._run_worker,
            args=(action, params),
            daemon=True,
        )
        thread.start()
        return True

    def cancel(self) -> bool:
        with self._lock:
            if self._status.state != "running":
                return False
            if self._cancel_event:
                self._cancel_event.set()
            return True

    def _make_progress_callback(self) -> ProgressCallback:
        def on_progress(
            *,
            step: int,
            total: int,
            message: str,
            log_append: str | None = None,
            qrcode_refreshed_at: int | None = None,
        ) -> None:
            with self._lock:
                self._status.progress_step = step
                self._status.progress_total = total
                self._status.progress_message = message
                self._status.message = message
                if log_append:
                    current = self._status.log.strip()
                    self._status.log = f"{current}\n{log_append}".strip() if current else log_append
                if qrcode_refreshed_at is not None:
                    result = dict(self._status.result or {})
                    result["qrcode_refreshed_at"] = qrcode_refreshed_at
                    self._status.result = result

        return on_progress

    def _run_worker(self, action: str, params: dict[str, Any]) -> None:
        on_progress = self._make_progress_callback()
        cancel_event = self._cancel_event
        try:
            payload = run_action(
                action,
                params,
                on_progress=on_progress,
                cancel_event=cancel_event,
            )
            with self._lock:
                self._status.state = "success" if payload.get("ok", True) else "error"
                self._status.finished_at = int(time.time())
                self._status.message = str(payload.get("message") or "完成")
                if payload.get("log"):
                    self._status.log = sanitize_log(str(payload.get("log")))
                self._status.result = payload.get("result")
                if self._status.progress_total:
                    self._status.progress_step = self._status.progress_total
        except LoginCancelledError:
            with self._lock:
                self._status.state = "idle"
                self._status.finished_at = int(time.time())
                self._status.message = "已取消扫码登录"
                self._status.log = "登录流程已结束"
                self._status.result = None
        except Exception as exc:
            with self._lock:
                self._status.state = "error"
                self._status.finished_at = int(time.time())
                self._status.message = friendly_error(exc)
                self._status.log = sanitize_log(traceback.format_exc()) or friendly_error(exc)


runner = JobRunner()
