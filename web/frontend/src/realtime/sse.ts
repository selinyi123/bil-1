// @ts-nocheck
/* eslint-disable */
/** Migrated from web/static/app.js — logic preserved. */

import { state } from "../state";
import { ensureAutoCountdown, ensureAutoPolling, mergeAutoLogs, renderAutoDock } from "../auto/index";
import { appendJobLogChunk, applyRunningJobView, finishJobOnce, mergeJobProgress, startPolling, stopJobPolling, updateJobUI } from "../jobs/index";

export const SSE_WATCHDOG_MS = 45000;

export const SSE_RECONNECT_MS = 3000;

export function markSseActive() {
  state.sseLastActive = Date.now();
}

export function stopSseWatchdog() {
  if (state.sseWatchdog) {
    window.clearInterval(state.sseWatchdog);
    state.sseWatchdog = null;
  }
}

export function startSseWatchdog() {
  stopSseWatchdog();
  state.sseWatchdog = window.setInterval(() => {
    if (!state.sseHealthy) return;
    if (Date.now() - state.sseLastActive > SSE_WATCHDOG_MS) {
      console.warn("SSE heartbeat timeout, fallback to polling");
      fallbackToPolling("heartbeat-timeout");
    }
  }, 5000);
}

export function closeEventSource() {
  if (state.eventSource) {
    try {
      state.eventSource.close();
    } catch {
      /* ignore */
    }
    state.eventSource = null;
  }
  stopSseWatchdog();
  state.sseHealthy = false;
}

export function fallbackToPolling(reason) {
  closeEventSource();
  // 浏览器不支持 EventSource 时不要循环重连
  if (reason !== "no-eventsource") {
    if (state.sseReconnectTimer) {
      window.clearTimeout(state.sseReconnectTimer);
    }
    state.sseReconnectTimer = window.setTimeout(() => {
      state.sseReconnectTimer = null;
      startRealtime();
    }, SSE_RECONNECT_MS);
  }
  const job = state.currentJob;
  if (job?.state === "running") startPolling();
  if (state.autoDockOpen || state.autoScheduler?.state === "running") {
    ensureAutoPolling();
  }
}

export function handleSseMessage(eventName, payload) {
  markSseActive();
  if (eventName === "heartbeat") return;

  if (eventName === "job.snapshot" || eventName === "job.created") {
    const job = {
      ...(state.currentJob || {}),
      ...payload,
      state: payload.state || (eventName === "job.created" ? "running" : payload.state),
    };
    if (eventName === "job.created") {
      // 新任务不得沿用上一任务的 log/result/进度
      job.log = "";
      job.result = payload.result && typeof payload.result === "object" ? payload.result : {};
      job.progress_step = payload.progress_step ?? 0;
      job.progress_total = payload.progress_total ?? 0;
      job.finished_at = null;
      job.message = payload.message || "任务已启动";
      state.lastFinishedJobKey = "";
    }
    if (job.state === "running") {
      applyRunningJobView(job);
    } else {
      state.currentJob = job;
      updateJobUI(job);
    }
    return;
  }

  if (eventName === "job.progress") {
    applyRunningJobView(mergeJobProgress(payload));
    return;
  }

  if (eventName === "job.log") {
    if (payload?.chunk) appendJobLogChunk(String(payload.chunk));
    return;
  }

  if (eventName === "job.terminal") {
    const job = {
      ...(state.currentJob || {}),
      ...payload,
      state: payload.state,
      id: payload.id ?? state.currentJob?.id,
    };
    void finishJobOnce(job);
    return;
  }

  if (eventName === "auto.snapshot") {
    if (Array.isArray(payload.logs)) {
      state.autoLogs = mergeAutoLogs(state.autoLogs, payload.logs);
    }
    renderAutoDock({ ...payload, logs: state.autoLogs });
    return;
  }

  if (eventName === "auto.log") {
    const row = {
      ts: payload.log_ts || "",
      level: payload.level || "info",
      message: payload.message || "",
    };
    state.autoLogs = mergeAutoLogs(state.autoLogs, [row]);
    if (state.autoScheduler) {
      renderAutoDock({ ...state.autoScheduler, logs: state.autoLogs });
    }
  }
}

export function startRealtime() {
  if (typeof EventSource === "undefined") {
    fallbackToPolling("no-eventsource");
    return;
  }
  if (state.eventSource && state.sseHealthy) return;
  // 已有连接正在建立时不要重复创建
  if (state.eventSource && state.eventSource.readyState === EventSource.CONNECTING) return;

  closeEventSource();
  try {
    const es = new EventSource("/api/events");
    state.eventSource = es;
    const bind = (name) => {
      es.addEventListener(name, (ev) => {
        try {
          const payload = JSON.parse(ev.data || "{}");
          state.sseHealthy = true;
          handleSseMessage(name, payload);
          // SSE 恢复后停掉 Job REST 轮询；Auto 倒计时保留
          if (state.polling) stopJobPolling();
          if (state.autoPollTimer) {
            window.clearInterval(state.autoPollTimer);
            state.autoPollTimer = null;
          }
        } catch (error) {
          console.error("SSE parse failed", name, error);
        }
      });
    };
    [
      "heartbeat",
      "job.snapshot",
      "job.created",
      "job.progress",
      "job.log",
      "job.terminal",
      "auto.snapshot",
      "auto.log",
    ].forEach(bind);
    es.onopen = () => {
      state.sseHealthy = true;
      markSseActive();
      startSseWatchdog();
      stopJobPolling();
      // 保留倒计时，仅停 REST 轮询
      if (state.autoPollTimer) {
        window.clearInterval(state.autoPollTimer);
        state.autoPollTimer = null;
      }
      ensureAutoCountdown();
    };
    es.onerror = () => {
      if (state.sseHealthy) {
        fallbackToPolling("eventsource-error");
        return;
      }
      // 尚未建连成功：关闭后稍后重试，并立刻用轮询兜底
      closeEventSource();
      const job = state.currentJob;
      if (job?.state === "running") startPolling();
      if (state.autoDockOpen || state.autoScheduler?.state === "running") {
        ensureAutoPolling();
      }
      if (!state.sseReconnectTimer) {
        state.sseReconnectTimer = window.setTimeout(() => {
          state.sseReconnectTimer = null;
          startRealtime();
        }, SSE_RECONNECT_MS);
      }
    };
    markSseActive();
    startSseWatchdog();
  } catch (error) {
    console.error(error);
    fallbackToPolling("eventsource-throw");
  }
}
