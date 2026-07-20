// @ts-nocheck
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

export function showToast(message, type = "info", detail = "", actions = []) {
  if (!toastStack || !message) return;
  const meta = TOAST_META[type] || TOAST_META.info;
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
  const duration =
    actions.length > 0
      ? Math.max(type === "error" ? 8000 : 4200, 10000)
      : type === "error"
        ? 8000
        : type === "running"
          ? 2400
          : 4200;
  const progress = toast.querySelector(".toast-progress");
  if (progress) progress.style.animationDuration = `${duration}ms`;
  toast.querySelector(".toast-close")?.addEventListener("click", () => toast.remove());
  toast.querySelectorAll("[data-toast-action]").forEach((button) => {
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

export function setInlineFeedback(element, message, type = "info", { autoHide = true } = {}) {
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
