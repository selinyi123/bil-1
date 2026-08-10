/* eslint-disable */
/** Migrated from web/static/app.js — logic preserved. */

import { INLINE_FEEDBACK_MS, inlineFeedbackTimers, toastStack } from "../dom";
import { prefersReducedMotion } from "../utils/motion";
import { escapeHtml } from "../utils/text";

export const TOAST_META = {
  success: { title: "执行成功", icon: "✓" },
  error: { title: "执行失败", icon: "!" },
  info: { title: "提示", icon: "i" },
  running: { title: "执行中", icon: "…" },
};

export interface ToastAction {
  label: string;
  onClick?: () => void;
}

export function showToast(message: string, type = "info", detail = "", actions: ToastAction[] = []) {
  if (!toastStack || !message) return;
  const meta = TOAST_META[type as keyof typeof TOAST_META] || TOAST_META.info;
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  const actionHtml = actions.length
    ? `<div class="toast-actions">${actions
        .map(
          (action, index) =>
            `<button type="button" class="btn btn-secondary btn-compact btn-pill toast-action-btn" data-toast-action="${index}">${escapeHtml(action.label)}</button>`
        )
        .join("")}</div>`
    : "";
  toast.innerHTML = `
    <div class="toast-icon" aria-hidden="true">${meta.icon}</div>
    <div class="toast-body">
      <p class="toast-title">${escapeHtml(meta.title)}</p>
      <p class="toast-message">${escapeHtml(message)}</p>
      ${detail ? `<p class="toast-detail">${escapeHtml(detail)}</p>` : ""}
      ${actionHtml}
    </div>
    <button type="button" class="toast-close" aria-label="关闭">×</button>
    <div class="toast-progress" aria-hidden="true"></div>`;
  // 错误类 toast 用 alert 角色即时播报，其余用 status（容器本身已 aria-live=polite）
  toast.setAttribute("role", type === "error" ? "alert" : "status");
  const duration =
    actions.length > 0
      ? Math.max(type === "error" ? 8000 : 4200, 10000)
      : type === "error"
        ? 8000
        : type === "running"
          ? 2400
          : 4200;
  const progress = toast.querySelector<HTMLElement>(".toast-progress");
  if (progress) progress.style.animationDuration = `${duration}ms`;
  toast.querySelector(".toast-close")?.addEventListener("click", () => toast.remove());
  toast.querySelectorAll<HTMLElement>("[data-toast-action]").forEach((button) => {
    button.addEventListener("click", () => {
      const action = actions[Number(button.dataset.toastAction)];
      toast.remove();
      action?.onClick?.();
    });
  });
  toastStack.appendChild(toast);
  window.setTimeout(() => {
    toast.classList.add("toast-hide");
    window.setTimeout(() => toast.remove(), 320);
  }, duration);
}

export function dismissRunningToasts() {
  if (!toastStack) return;
  toastStack.querySelectorAll(".toast-running").forEach((toast) => toast.remove());
}

export function setInlineFeedback(element: HTMLElement | null, message: string, type = "info", { autoHide = true }: { autoHide?: boolean } = {}) {
  if (!element) return;
  const existing = inlineFeedbackTimers.get(element);
  if (existing) window.clearTimeout(existing);

  if (!message) {
    element.hidden = true;
    element.textContent = "";
    element.className = "inline-feedback";
    return;
  }

  element.hidden = false;
  element.textContent = message;
  element.className = `inline-feedback inline-feedback--${type}`;
  if (!prefersReducedMotion()) {
    element.classList.remove("is-feedback-pop");
    void element.offsetWidth;
    element.classList.add("is-feedback-pop");
  }

  if (autoHide && type !== "info") {
    const timer = window.setTimeout(() => setInlineFeedback(element, "", "info"), INLINE_FEEDBACK_MS);
    inlineFeedbackTimers.set(element, timer);
  }
}
