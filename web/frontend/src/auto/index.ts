/* eslint-disable */
/** Migrated from web/static/app.js — logic preserved. */

import { state } from "../state";
import { fetchJSON } from "../api/client";
import { autoDock, autoDockBadge, autoDockCountdown, autoDockFatal, autoDockFatalText, autoDockHint, autoDockJob, autoDockPanel, autoDockPhase, autoDockPipeline, autoDockScheduler, autoDockStartBtn, autoDockStatus, autoDockStopBtn, autoDockToggle, autoDockToggleMeta } from "../dom";
import { openAppConfirm } from "../shell/confirm";
import { showToast } from "../shell/toast";
import { formatAutoCountdown } from "../utils/format";
import { prefersReducedMotion } from "../utils/motion";
import { sanitizeUserText, escapeHtml } from "../utils/text";
import type { AutoStatus } from "../types";

interface AutoNextSlot {
  at_unix?: number;
  hint?: string;
}

interface AutoJobProbe {
  job_state?: string;
  job_label?: string;
  job_action?: string;
}

interface AutoPipelineStep {
  index?: number;
  label?: string;
  action?: string;
  status?: string;
}

interface AutoPipeline {
  active?: boolean;
  steps?: AutoPipelineStep[];
}

interface AutoScheduleSlot {
  at?: string;
  label?: string;
  action_label?: string;
  actions?: Array<{ label?: string; action?: string }>;
}

/** next_slot 在 AutoStatus 中声明为 number|null，实际后端为对象形态，统一取对象形态。 */
function getNextSlot(status: AutoStatus | null | undefined): AutoNextSlot | null {
  const slot = status?.next_slot;
  return slot !== null && typeof slot === "object" ? (slot as AutoNextSlot) : null;
}

function getJobProbe(status: AutoStatus | null | undefined): AutoJobProbe {
  return (status?.job_probe as AutoJobProbe | null | undefined) || {};
}

export function setAutoDockOpen(open: boolean) {
  state.autoDockOpen = open;
  if (!autoDockPanel || !autoDockToggle) return;
  autoDockPanel.classList.toggle("is-open", open);
  autoDockPanel.setAttribute("aria-hidden", String(!open));
  autoDockToggle.setAttribute("aria-expanded", String(open));
  autoDock?.classList.toggle("open", open);
  if (open) {
    if (!prefersReducedMotion()) {
      autoDockPanel.classList.remove("is-entering");
      void autoDockPanel.offsetWidth;
      autoDockPanel.classList.add("is-entering");
    }
    fetchAutoStatus().catch(() => {});
    ensureAutoPolling();
    ensureAutoCountdown();
    tickAutoCountdown();
  } else {
    autoDockPanel.classList.remove("is-entering");
    if (!(state.autoScheduler && state.autoScheduler.state === "running")) {
      stopAutoPolling();
    }
  }
}

export function getAutoCountdownSeconds(targetUnix: string | number | null | undefined) {
  if (!targetUnix) return null;
  const nowSec = Math.floor((Date.now() + state.autoServerSkewMs) / 1000);
  return Math.max(0, Number(targetUnix) - nowSec);
}

export function toggleAutoDock(forceOpen?: boolean) {
  const next = typeof forceOpen === "boolean" ? forceOpen : !state.autoDockOpen;
  setAutoDockOpen(next);
}

export function resolveAutoSchedulerText(status: AutoStatus | null | undefined) {
  const s: Partial<AutoStatus> = status || {};
  const schedulerState = String(s.state || "idle");
  if (schedulerState === "fatal") {
    return sanitizeUserText(s.fatal_error || s.message || "已停机");
  }
  if (schedulerState !== "running") {
    return sanitizeUserText(s.state_label || s.message || "尚未启动");
  }
  const phase = sanitizeUserText(s.current_phase || "");
  if (phase && phase !== "—") return phase;
  return sanitizeUserText(s.message || "调度运行中");
}

export function resolveAutoJobText(status: AutoStatus | null | undefined) {
  const jobProbe = getJobProbe(status);
  const jobState = String(jobProbe.job_state || "idle");
  const jobLabel = sanitizeUserText(jobProbe.job_label || jobProbe.job_action || "");
  if (jobState === "running") {
    return jobLabel ? `运行中 · ${jobLabel}` : "运行中";
  }
  if (jobState === "idle") return "空闲";
  if (jobState === "success") return jobLabel ? `刚完成 · ${jobLabel}` : "刚完成";
  if (jobState === "error") return jobLabel ? `出错 · ${jobLabel}` : "出错";
  return jobLabel || jobState || "—";
}

export function resolveAutoJobTone(status: AutoStatus | null | undefined) {
  const jobState = String(getJobProbe(status).job_state || "idle");
  if (jobState === "running") return "running";
  if (jobState === "error") return "error";
  if (jobState === "success") return "success";
  return "idle";
}

export function renderAutoPipeline(pipeline: AutoPipeline | null | undefined) {
  if (!autoDockPipeline) return;
  const steps = Array.isArray(pipeline?.steps) ? pipeline.steps : [];
  if (!steps.length) {
    autoDockPipeline.innerHTML = "";
    return;
  }
  autoDockPipeline.innerHTML = steps
    .map((step, index) => {
      const label = escapeHtml(sanitizeUserText(step.label || step.action || "") || "");
      const rawStatus = String(step.status || "pending");
      const status = ["pending", "running", "success", "error", "skipped", "waiting"].includes(rawStatus)
        ? rawStatus
        : "pending";
      const stepIndex = Number.isFinite(step.index ?? NaN) ? Number(step.index) + 1 : index + 1;
      return `<div class="auto-dock-step" data-status="${escapeHtml(status)}" data-index="${stepIndex}"><span class="auto-dock-step-label">${label}</span></div>`;
    })
    .join("");
}

export function updateAutoCollapsedMeta(status: AutoStatus | null | undefined) {
  if (!autoDockToggleMeta) return;
  const schedulerState = String(status?.state || "idle");
  if (schedulerState === "running") {
    const countdown = formatAutoCountdown(getNextSlot(status)?.at_unix);
    autoDockToggleMeta.hidden = false;
    autoDockToggleMeta.textContent = countdown === "—" ? "…" : countdown;
    return;
  }
  // fatal / idle：角标或默认文案已够，折叠态不再重复「已停机」
  autoDockToggleMeta.hidden = true;
  autoDockToggleMeta.textContent = "";
}

export function renderAutoDock(status: AutoStatus) {
  if (!status) return;
  state.autoScheduler = status;
  if (status.server_now_unix) {
    state.autoServerSkewMs = Number(status.server_now_unix) * 1000 - Date.now();
  }

  const schedulerState = String(status.state || "idle");
  const stateLabel = sanitizeUserText(status.state_label || status.message || "尚未启动");
  const message = sanitizeUserText(status.message || "");
  const phase = sanitizeUserText(status.current_phase || "—");
  const hint = sanitizeUserText(status.next_hint || getNextSlot(status)?.hint || "—");

  if (autoDockStatus) {
    // 头部只保留短状态，长进度细节交给「调度 / 抽奖任务」行
    autoDockStatus.textContent =
      schedulerState === "running"
        ? sanitizeUserText(status.state_label || "调度器运行中")
        : message || stateLabel;
  }
  if (autoDockPhase) {
    autoDockPhase.textContent = phase;
    autoDockPhase.classList.toggle("is-live", schedulerState === "running");
  }
  if (autoDockHint) {
    autoDockHint.textContent = hint;
  }
  const hero = document.querySelector(".auto-dock-hero");
  const pipeline = status.refresh_pipeline as AutoPipeline | null | undefined;
  const pipelineBlock = document.querySelector(".auto-dock-pipeline-block");
  const countdownSec = getAutoCountdownSeconds(getNextSlot(status)?.at_unix);
  const urgent = schedulerState === "running" && countdownSec !== null && countdownSec > 0 && countdownSec < 60;
  if (hero) {
    hero.classList.toggle("is-live", schedulerState === "running");
    hero.classList.toggle("is-urgent", urgent);
  }
  if (pipelineBlock) {
    pipelineBlock.classList.toggle("is-active", Boolean(pipeline?.active));
  }
  if (autoDockScheduler) {
    autoDockScheduler.textContent = resolveAutoSchedulerText(status);
    autoDockScheduler.dataset.tone = schedulerState === "fatal" ? "error" : schedulerState === "running" ? "running" : "idle";
  }
  if (autoDockJob) {
    autoDockJob.textContent = resolveAutoJobText(status);
    autoDockJob.dataset.tone = resolveAutoJobTone(status);
  }
  tickAutoCountdown();
  renderAutoPipeline(pipeline);
  updateAutoCollapsedMeta(status);

  const running = schedulerState === "running";
  const fatal = schedulerState === "fatal";

  autoDock?.classList.toggle("fatal", fatal);
  autoDock?.classList.toggle("is-running", running);
  if (autoDockBadge) {
    autoDockBadge.hidden = !running && !fatal;
    autoDockBadge.textContent = fatal ? "已停机" : "运行中";
    autoDockBadge.classList.toggle("fatal", fatal);
  }
  if (autoDockFatal) {
    autoDockFatal.hidden = !fatal;
  }
  if (autoDockFatalText) {
    autoDockFatalText.textContent = sanitizeUserText(status.fatal_error || "");
  }
  if (autoDockStartBtn) {
    autoDockStartBtn.hidden = running;
  }
  if (autoDockStopBtn) {
    autoDockStopBtn.hidden = !running;
  }

  if (running || state.autoDockOpen) {
    if (state.sseHealthy) {
      ensureAutoCountdown();
      // SSE 健康时停 2s 轮询，倒计时仍本地跑
      if (state.autoPollTimer) {
        window.clearInterval(state.autoPollTimer);
        state.autoPollTimer = null;
      }
    } else {
      ensureAutoPolling();
      ensureAutoCountdown();
    }
  } else if (!state.sseHealthy) {
    stopAutoPolling();
  } else {
    ensureAutoCountdown();
  }
}

export function tickAutoCountdown() {
  const status = state.autoScheduler;
  if (!autoDockCountdown) return;
  const targetUnix = getNextSlot(status)?.at_unix;
  autoDockCountdown.textContent = formatAutoCountdown(targetUnix);
  const countdownSec = getAutoCountdownSeconds(targetUnix);
  const running = String(status?.state || "") === "running";
  const urgent = running && countdownSec !== null && countdownSec > 0 && countdownSec < 60;
  autoDockCountdown.classList.toggle("is-urgent", urgent);
  document.querySelector(".auto-dock-hero")?.classList.toggle("is-urgent", urgent);
  updateAutoCollapsedMeta(status);
}

export function ensureAutoCountdown() {
  if (state.autoCountdownTimer) return;
  state.autoCountdownTimer = window.setInterval(tickAutoCountdown, 1000);
}

export function ensureAutoPolling() {
  if (state.sseHealthy && state.eventSource) {
    ensureAutoCountdown();
    return;
  }
  if (!state.autoPollTimer) {
    state.autoPollTimer = window.setInterval(() => {
      if (state.sseHealthy && state.eventSource) return;
      fetchAutoStatus().catch(() => {});
    }, 2000);
  }
  ensureAutoCountdown();
}

export function stopAutoPolling() {
  if (state.autoPollTimer) {
    window.clearInterval(state.autoPollTimer);
    state.autoPollTimer = null;
  }
  if (state.autoCountdownTimer) {
    window.clearInterval(state.autoCountdownTimer);
    state.autoCountdownTimer = null;
  }
}

export async function fetchAutoStatus() {
  const status = await fetchJSON<AutoStatus>("/api/auto/status");
  renderAutoDock(status);
  fetchAutoSchedule().catch(() => {});
  return status;
}

/** 拉取并渲染接下来最近的定时计划（只读展示）。 */
export async function fetchAutoSchedule() {
  const data = await fetchJSON<{ slots?: AutoScheduleSlot[] }>("/api/auto/schedule");
  renderAutoSchedule(data?.slots || []);
}

export function renderAutoSchedule(slots: AutoScheduleSlot[] | null | undefined) {
  if (!autoDockPanel) return;
  let container = autoDockPanel.querySelector(".extra-schedule");
  if (!container) {
    container = document.createElement("div");
    container.className = "extra-schedule";
    autoDockPanel.appendChild(container);
  }
  if (!Array.isArray(slots) || !slots.length) {
    container.innerHTML = '<p class="extra-schedule-empty">暂无定时计划（调度器未配置触发时间）。</p>';
    return;
  }
  container.innerHTML = `
    <p class="auto-dock-eyebrow" style="margin-top: 14px;">Upcoming</p>
    <div class="extra-schedule-list">
      ${slots
        .map(
          (slot) => `
        <div class="extra-schedule-item">
          <span class="extra-schedule-when">${escapeHtml(String(slot.at || ""))}</span>
          <span class="extra-schedule-label">${escapeHtml(String(slot.label || slot.action_label || ""))}</span>
          <span class="extra-schedule-actions">${escapeHtml(
            (slot.actions || []).map((a) => a?.label || a?.action || "").filter(Boolean).join(" → "),
          )}</span>
        </div>`,
        )
        .join("")}
    </div>`;
}

export async function startAutoScheduler() {
  await fetchJSON("/api/auto/start", { method: "POST" });
  await fetchAutoStatus();
  ensureAutoPolling();
  showToast("定时调度已启动", "success");
}

export async function stopAutoScheduler() {
  const ok = await openAppConfirm({
    eyebrow: "定时点击",
    title: "确定停止调度？",
    desc: "停止调度只会停下定时点击监视器，不会取消正在运行的抽奖任务。",
    confirmLabel: "停止调度",
    cancelLabel: "继续运行",
  });
  if (!ok) return;
  await fetchJSON("/api/auto/stop", { method: "POST" });
  await fetchAutoStatus();
  showToast("定时调度已停止", "info");
}

export function bindAutoDock() {
  autoDockToggle?.addEventListener("click", () => toggleAutoDock());
  document.getElementById("auto-dock-collapse")?.addEventListener("click", () => toggleAutoDock(false));
  autoDockStartBtn?.addEventListener("click", () => {
    const startBtn = autoDockStartBtn as HTMLButtonElement;
    startBtn.disabled = true;
    startAutoScheduler()
      .catch((error) => showToast(sanitizeUserText(error.message || error) || "启动失败", "error"))
      .finally(() => {
        startBtn.disabled = false;
      });
  });
  autoDockStopBtn?.addEventListener("click", () => {
    const stopBtn = autoDockStopBtn as HTMLButtonElement;
    stopBtn.disabled = true;
    stopAutoScheduler()
      .catch((error) => showToast(sanitizeUserText(error.message || error) || "停止失败", "error"))
      .finally(() => {
        stopBtn.disabled = false;
      });
  });
}

export function autoLogKey(row: Record<string, unknown> | null | undefined) {
  return `${row?.ts || ""}|${row?.level || ""}|${row?.message || ""}`;
}

export function mergeAutoLogs(existing: Array<Record<string, unknown>> | null | undefined, incoming: Array<Record<string, unknown>> | null | undefined) {
  const map = new Map();
  for (const row of existing || []) {
    if (!row) continue;
    map.set(autoLogKey(row), row);
  }
  for (const row of incoming || []) {
    if (!row) continue;
    map.set(autoLogKey(row), row);
  }
  return Array.from(map.values()).slice(-80);
}
