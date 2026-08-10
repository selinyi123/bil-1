/* eslint-disable */
/** Migrated from web/static/app.js — logic preserved. */

import { appConfirmBackdrop, appConfirmBullets, appConfirmCancel, appConfirmDesc, appConfirmEyebrow, appConfirmModal, appConfirmSecondary, appConfirmTitle, appConfirmYes } from "../dom";
import { switchSection } from "../shell/nav";
import { escapeHtml } from "../utils/text";

export function closeAppConfirm() {
  if (!appConfirmModal) return;
  appConfirmModal.hidden = true;
  document.body.classList.remove("modal-open");
}

export interface ConfirmOptions {
  eyebrow?: string;
  title?: string;
  desc?: string;
  bullets?: string[];
  confirmLabel?: string;
  cancelLabel?: string;
  secondaryLabel?: string;
  danger?: boolean;
  onSecondary?: (() => void) | null;
}

export function openAppConfirm({
  eyebrow = "",
  title = "",
  desc = "",
  bullets = [],
  confirmLabel = "确认",
  cancelLabel = "取消",
  secondaryLabel = "",
  danger = false,
  onSecondary = null,
}: ConfirmOptions = {}) {
  return new Promise<boolean>((resolve) => {
    if (!appConfirmModal || !appConfirmCancel || !appConfirmYes) {
      resolve(window.confirm(title || "确认继续？"));
      return;
    }
    const lastFocus = document.activeElement as HTMLElement | null;

    const cleanup = () => {
      closeAppConfirm();
      lastFocus?.focus();
      appConfirmCancel?.removeEventListener("click", onCancel);
      appConfirmYes?.removeEventListener("click", onConfirm);
      appConfirmBackdrop?.removeEventListener("click", onCancel);
      appConfirmSecondary?.removeEventListener("click", onSecondaryClick);
      document.removeEventListener("keydown", onKeyDown);
    };

    const onCancel = () => {
      cleanup();
      resolve(false);
    };

    const onConfirm = () => {
      cleanup();
      resolve(true);
    };

    const onSecondaryClick = () => {
      cleanup();
      try {
        onSecondary?.();
      } catch {
        /* ignore */
      }
      resolve(false);
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onCancel();
        return;
      }
      if (event.key !== "Tab") return;
      // Tab 焦点陷阱：循环在对话框内可聚焦元素之间
      const focusable = [
        ...appConfirmModal!.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        ),
      ].filter((el) => !el.hidden && el.getAttribute("aria-hidden") !== "true");
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    if (appConfirmEyebrow) appConfirmEyebrow.textContent = eyebrow;
    if (appConfirmTitle) appConfirmTitle.textContent = title;
    if (appConfirmDesc) {
      if (desc) {
        appConfirmDesc.hidden = false;
        appConfirmDesc.textContent = desc;
      } else {
        appConfirmDesc.hidden = true;
        appConfirmDesc.textContent = "";
      }
    }
    if (appConfirmBullets) {
      if (bullets.length) {
        appConfirmBullets.hidden = false;
        appConfirmBullets.innerHTML = bullets.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
      } else {
        appConfirmBullets.hidden = true;
        appConfirmBullets.innerHTML = "";
      }
    }
    appConfirmCancel.textContent = cancelLabel;
    appConfirmYes.textContent = confirmLabel;
    appConfirmYes.classList.toggle("btn-danger", Boolean(danger));
    if (appConfirmSecondary) {
      const showSecondary = Boolean(secondaryLabel);
      appConfirmSecondary.toggleAttribute("hidden", !showSecondary);
      appConfirmSecondary.textContent = showSecondary ? secondaryLabel : "";
    }

    appConfirmModal.hidden = false;
    document.body.classList.add("modal-open");
    appConfirmCancel.addEventListener("click", onCancel);
    appConfirmYes.addEventListener("click", onConfirm);
    appConfirmBackdrop?.addEventListener("click", onCancel);
    if (secondaryLabel && appConfirmSecondary) {
      appConfirmSecondary.addEventListener("click", onSecondaryClick);
    }
    document.addEventListener("keydown", onKeyDown);
    appConfirmCancel.focus();
  });
}

export function confirmRefreshAll() {
  return openAppConfirm({
    eyebrow: "数据源",
    title: "确认一键更新全部数据源？",
    bullets: [
      "将并行检查全部 UP 合集，请求量较大，容易触发 B 站风控",
      "日常更推荐在「数据源」页对单个 UP 点「更新此源」",
      "适合长时间未打开、想一次性扫完全部源时使用",
    ],
    confirmLabel: "仍要一键更新",
    cancelLabel: "取消",
    secondaryLabel: "去数据源页",
    onSecondary: () => switchSection("sources"),
  });
}
