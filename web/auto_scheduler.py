"""定时点击调度器：进程内直连 JobRunner，只点 4 个按钮，撞车即停，绝不 cancel。"""

from __future__ import annotations

import threading
import time
import traceback
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from web.auto_config import (
    ACTION_LABELS,
    ALLOWED_CLICK_ACTIONS,
    JOB_POLL_INTERVAL_SEC,
    JOB_POLL_TIMEOUT_SEC,
    REFRESH_HOURS,
    TRIPLE_MINUTES,
)
from web.job_runner import JobRunner, runner

CN_TZ = ZoneInfo("Asia/Shanghai")
SchedulerState = Literal["idle", "running", "stopped", "fatal"]
STATE_LABELS = {
    "idle": "尚未启动",
    "running": "调度运行中",
    "stopped": "已停止",
    "fatal": "已停机",
}
REFRESH_STEPS = (
    {"action": "refresh_all", "label": "一键更新活动链接"},
    {"action": "refresh_watch", "label": "更新监控用户动态"},
    {"action": "refresh_status", "label": "刷新任务状态"},
)


class CollisionError(RuntimeError):
    """抽奖端已有任务在跑，自动调度必须立即停机。"""


@dataclass
class LogEntry:
    ts: str
    level: str
    message: str


@dataclass
class SchedulerStatus:
    state: SchedulerState = "idle"
    message: str = "尚未启动"
    started_at: str | None = None
    stopped_at: str | None = None
    fatal_error: str | None = None
    last_tick_at: str | None = None
    current_phase: str = ""
    next_hint: str = ""
    last_click: dict[str, Any] | None = None
    refresh_batch_key: str | None = None
    triple_slot_key: str | None = None
    refresh_pipeline: dict[str, Any] = field(default_factory=dict)
    next_slot: dict[str, Any] | None = None
    job_probe: dict[str, Any] | None = None
    server_now: str = ""
    server_now_unix: int = 0
    logs: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "state_label": STATE_LABELS.get(self.state, self.state),
            "message": self.message,
            "started_at": self.started_at,
            "stopped_at": self.stopped_at,
            "fatal_error": self.fatal_error,
            "last_tick_at": self.last_tick_at,
            "current_phase": self.current_phase,
            "next_hint": self.next_hint,
            "next_slot": self.next_slot,
            "last_click": self.last_click,
            "refresh_batch_key": self.refresh_batch_key,
            "triple_slot_key": self.triple_slot_key,
            "refresh_pipeline": self.refresh_pipeline or _idle_pipeline(),
            "job_probe": self.job_probe,
            "server_now": self.server_now,
            "server_now_unix": self.server_now_unix,
            "logs": list(self.logs),
            "schedule": {
                "refresh_hours": sorted(REFRESH_HOURS),
                "triple_minutes": sorted(TRIPLE_MINUTES),
                "actions": [
                    {"action": key, "label": ACTION_LABELS[key]}
                    for key in ("refresh_all", "refresh_watch", "refresh_status", "participate_triple")
                ],
            },
        }


class AutoScheduler:
    def __init__(self, job_runner: JobRunner | None = None) -> None:
        self._runner = job_runner or runner
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._logs: deque[LogEntry] = deque(maxlen=200)
        self._status = SchedulerStatus(refresh_pipeline=_idle_pipeline())
        self._done_refresh: set[str] = set()
        self._done_triple: set[str] = set()

    def get_status(self) -> dict[str, Any]:
        now = datetime.now(CN_TZ)
        slot = _next_slot(now)
        probe = _probe_job(self._runner)
        with self._lock:
            self._status.logs = [
                {"ts": e.ts, "level": e.level, "message": e.message} for e in list(self._logs)[-80:]
            ]
            self._status.next_slot = slot
            self._status.next_hint = slot.get("hint") or ""
            self._status.job_probe = probe
            self._status.server_now = _now_iso()
            self._status.server_now_unix = int(now.timestamp())
            if not self._status.refresh_pipeline:
                self._status.refresh_pipeline = _idle_pipeline()
            return self._status.to_dict()

    def start(self) -> dict[str, Any]:
        with self._lock:
            if self._thread and self._thread.is_alive() and self._status.state == "running":
                raise RuntimeError("调度器已在运行")
            if self._status.state == "fatal":
                self._status.fatal_error = None
            self._stop_event.clear()
            self._status.state = "running"
            self._status.message = "调度器运行中"
            self._status.started_at = _now_iso()
            self._status.stopped_at = None
            self._status.fatal_error = None
            self._status.current_phase = "等待下一刻度"
            self._status.refresh_pipeline = _idle_pipeline()
            self._thread = threading.Thread(target=self._loop, name="binggo-auto-scheduler", daemon=True)
            self._thread.start()
        self._log("info", "调度器已启动（仅点击 4 个按钮，不干涉抽奖程序其它功能）")
        return self.get_status()

    def stop(self, *, reason: str = "用户停止") -> dict[str, Any]:
        """只停止本调度器，绝不取消抽奖端任务。"""
        self._stop_event.set()
        with self._lock:
            if self._status.state == "running":
                self._status.state = "stopped"
                self._status.message = reason
                self._status.stopped_at = _now_iso()
                self._status.current_phase = ""
                self._status.refresh_pipeline = _idle_pipeline()
        self._log("warn", f"调度器已停止：{reason}")
        return self.get_status()

    def _fatal(self, message: str) -> None:
        self._stop_event.set()
        with self._lock:
            self._status.state = "fatal"
            self._status.message = "因任务撞车或严重错误已停机"
            self._status.fatal_error = message
            self._status.stopped_at = _now_iso()
            self._status.current_phase = "已停机"
            self._status.refresh_pipeline = {
                **(self._status.refresh_pipeline or _idle_pipeline()),
                "active": False,
            }
        self._log("error", f"致命停机：{message}")

    def _log(self, level: str, message: str) -> None:
        entry = LogEntry(ts=_now_iso(), level=level, message=message)
        with self._lock:
            self._logs.append(entry)

    def _set_phase(self, phase: str, message: str | None = None) -> None:
        with self._lock:
            self._status.current_phase = phase
            if message is not None:
                self._status.message = message
            slot = _next_slot(datetime.now(CN_TZ))
            self._status.next_slot = slot
            self._status.next_hint = slot.get("hint") or ""

    def _set_pipeline(self, *, active: bool, step_index: int = -1, waiting: bool = False) -> None:
        steps = []
        for i, item in enumerate(REFRESH_STEPS):
            if not active or step_index < 0:
                status = "pending"
            elif i < step_index:
                status = "done"
            elif i == step_index:
                status = "waiting" if waiting else "active"
            else:
                status = "pending"
            steps.append({**item, "status": status, "index": i})
        with self._lock:
            self._status.refresh_pipeline = {
                "active": active,
                "step_index": step_index,
                "waiting": waiting,
                "steps": steps,
            }

    def _loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                now = datetime.now(CN_TZ)
                with self._lock:
                    self._status.last_tick_at = _now_iso()
                    slot = _next_slot(now)
                    self._status.next_slot = slot
                    self._status.next_hint = slot.get("hint") or ""

                if now.hour in REFRESH_HOURS and now.minute == 0:
                    key = f"{now:%Y-%m-%d-%H}"
                    if key not in self._done_refresh:
                        self._run_refresh_batch(key)
                        continue

                if now.hour not in REFRESH_HOURS and now.minute in TRIPLE_MINUTES:
                    key = f"{now:%Y-%m-%d-%H-%M}"
                    if key not in self._done_triple:
                        self._run_triple_slot(key)
                        continue

                if self._status.state == "running":
                    self._set_phase("等待下一刻度", "调度器运行中")
                self._stop_event.wait(1.0)
        except CollisionError as exc:
            self._fatal(f"任务撞车：{exc}")
        except Exception as exc:
            self._fatal(f"未预期错误：{exc}\n{traceback.format_exc()[-800:]}")

    def _run_refresh_batch(self, key: str) -> None:
        self._set_phase("刷新批次", f"开始刷新批次 {key}")
        self._log("info", f"刷新批次开始 {key}：一键更新 → 监控动态 → 刷新状态")
        self._set_pipeline(active=True, step_index=0, waiting=False)
        actions = ("refresh_all", "refresh_watch", "refresh_status")
        try:
            for index, action in enumerate(actions):
                if self._stop_event.is_set():
                    self._set_pipeline(active=False)
                    return
                self._set_pipeline(active=True, step_index=index, waiting=False)
                try:
                    self._click_and_wait(action, pipeline_index=index)
                except CollisionError:
                    raise
                except Exception as exc:
                    if _is_hard_failure(exc):
                        raise
                    self._log("warn", f"「{ACTION_LABELS.get(action, action)}」业务结束：{exc}，继续下一项")
            self._done_refresh.add(key)
            with self._lock:
                self._status.refresh_batch_key = key
            self._log("info", f"刷新批次完成 {key}")
            self._set_pipeline(active=False)
            self._set_phase("等待下一刻度", "刷新批次已完成")
        except CollisionError:
            raise
        except Exception as exc:
            if _is_hard_failure(exc):
                self._fatal(str(exc))
                return
            self._log("error", f"刷新批次中断 {key}：{exc}")
            self._done_refresh.add(key)
            self._set_pipeline(active=False)
            self._set_phase("等待下一刻度", f"刷新批次异常已跳过：{exc}")

    def _run_triple_slot(self, key: str) -> None:
        self._set_pipeline(active=False)
        self._set_phase("三连参与", f"触发三连参与 {key}")
        self._log("info", f"三连参与刻度 {key}")
        try:
            outcome = self._click_and_wait("participate_triple")
            self._done_triple.add(key)
            with self._lock:
                self._status.triple_slot_key = key
            if outcome and outcome.get("skipped"):
                msg = str(outcome.get("message") or "当前没有可参与活动，已跳过")
                self._log("info", f"三连参与已跳过：{msg}")
                self._set_phase("等待下一刻度", msg)
            else:
                self._set_phase("等待下一刻度", "三连参与已完成")
        except CollisionError:
            raise
        except Exception as exc:
            if _is_hard_failure(exc):
                self._fatal(str(exc))
                return
            self._log("info", f"三连参与已跳过：{exc}")
            self._done_triple.add(key)
            self._set_phase("等待下一刻度", f"已跳过：{exc}")

    def _click_and_wait(self, action: str, *, pipeline_index: int | None = None) -> dict[str, Any]:
        if action not in ALLOWED_CLICK_ACTIONS:
            raise ValueError(f"禁止的操作：{action}")

        label = ACTION_LABELS.get(action, action)
        self._set_phase(f"点击：{label}", f"正在点击「{label}」")
        self._log("info", f"点击按钮：{label} ({action})")

        if self._runner.is_running():
            current = self._runner.get_status().to_dict()
            raise CollisionError(
                f"准备点击「{label}」时发现抽奖端仍有任务在运行"
                f"（action={current.get('action')}, message={current.get('message')}）"
            )

        if not self._runner.start(action, {"from_auto": True} if action == "participate_triple" else {}):
            raise CollisionError(f"点击「{label}」失败：已有任务正在运行")

        with self._lock:
            self._status.last_click = {
                "action": action,
                "label": label,
                "at": _now_iso(),
                "response_ok": True,
            }

        if pipeline_index is not None:
            self._set_pipeline(active=True, step_index=pipeline_index, waiting=True)

        final = self._wait_until_idle(label)
        state = str(final.get("state") or "")
        msg = str(final.get("message") or "")
        result = final.get("result") if isinstance(final.get("result"), dict) else {}
        if result.get("skipped") or (
            action == "participate_triple" and state == "error" and _is_triple_empty_skip(msg)
        ):
            return {"skipped": True, "message": msg, "job": final}
        if state == "error":
            raise RuntimeError(msg or f"「{label}」以 error 结束")
        return {"skipped": False, "message": msg, "job": final}

    def _wait_until_idle(self, label: str) -> dict[str, Any]:
        """只读轮询 JobRunner，直到任务不再 running。绝不 cancel。"""
        deadline = time.monotonic() + JOB_POLL_TIMEOUT_SEC
        self._set_phase(f"等待结束：{label}", f"已点击「{label}」，等待抽奖端自行结束…")
        time.sleep(0.8)
        last: dict[str, Any] = {}
        while not self._stop_event.is_set():
            if time.monotonic() > deadline:
                raise RuntimeError(f"等待「{label}」超时（超过 {int(JOB_POLL_TIMEOUT_SEC)} 秒）")
            job = self._runner.get_status().to_dict()
            last = job
            state = str(job.get("state") or "")
            if state != "running":
                msg = str(job.get("message") or state or "done")
                self._log("info", f"「{label}」已结束：state={state} · {msg}")
                return job
            detail = str(job.get("progress_message") or job.get("message") or "")
            if detail:
                self._set_phase(f"等待结束：{label}", detail)
            self._stop_event.wait(JOB_POLL_INTERVAL_SEC)
        return last


def _probe_job(job_runner: JobRunner) -> dict[str, Any]:
    job = job_runner.get_status().to_dict()
    state = str(job.get("state") or "idle")
    return {
        "ok": True,
        "reachable": True,
        "job_state": state,
        "job_action": str(job.get("action") or ""),
        "job_message": str(job.get("message") or ""),
        "job_label": str(job.get("label") or ""),
        "checked_at": _now_iso(),
    }


def _idle_pipeline() -> dict[str, Any]:
    return {
        "active": False,
        "step_index": -1,
        "waiting": False,
        "steps": [{**item, "status": "pending", "index": i} for i, item in enumerate(REFRESH_STEPS)],
    }


def _is_triple_empty_skip(message: str) -> bool:
    text = str(message or "")
    markers = ("没有可参与", "当前列表没有", "无可参与", "已跳过")
    return any(marker in text for marker in markers)


def _is_hard_failure(exc: BaseException) -> bool:
    if isinstance(exc, CollisionError):
        return True
    if _is_triple_empty_skip(str(exc)):
        return False
    text = str(exc)
    soft_markers = ("没有可参与", "当前列表没有", "无可参与", "已跳过")
    if any(m in text for m in soft_markers):
        return False
    hard_markers = (
        "连接",
        "timeout",
        "Timeout",
        "ConnectError",
        "等待「",
        "HTTP 5",
        "扫码登录",
        "LLM",
        "Cookie",
        "401",
    )
    return any(m in text for m in hard_markers)


def _now_iso() -> str:
    return datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _next_slot(now: datetime) -> dict[str, Any]:
    for offset_min in range(1, 24 * 60 + 1):
        candidate = now.replace(second=0, microsecond=0) + timedelta(minutes=offset_min)
        h, m = candidate.hour, candidate.minute
        if h in REFRESH_HOURS and m == 0:
            return {
                "kind": "refresh",
                "label": "刷新批次",
                "action": "refresh_all",
                "action_label": ACTION_LABELS["refresh_all"],
                "actions": [
                    {"action": item["action"], "label": item["label"]}
                    for item in REFRESH_STEPS
                ],
                "at": candidate.strftime("%Y-%m-%d %H:%M:%S"),
                "at_unix": int(candidate.timestamp()),
                "hour": h,
                "minute": m,
                "hint": f"下次刷新批次约 {h:02d}:00（一键更新→监控→状态）",
            }
        if h not in REFRESH_HOURS and m in TRIPLE_MINUTES:
            return {
                "kind": "triple",
                "label": "三连参与",
                "action": "participate_triple",
                "action_label": ACTION_LABELS["participate_triple"],
                "actions": [
                    {"action": "participate_triple", "label": ACTION_LABELS["participate_triple"]}
                ],
                "at": candidate.strftime("%Y-%m-%d %H:%M:%S"),
                "at_unix": int(candidate.timestamp()),
                "hour": h,
                "minute": m,
                "hint": f"下次三连参与约 {h:02d}:{m:02d}",
            }
    return {
        "kind": "none",
        "label": "暂无",
        "action": None,
        "action_label": "暂无",
        "actions": [],
        "at": None,
        "at_unix": None,
        "hint": "暂无下一刻度",
    }


auto_scheduler = AutoScheduler()
