/* eslint-disable */
/** Migrated from web/static/app.js — logic preserved. */

import { appConfirmBullets, appConfirmCancel, appConfirmDesc, appConfirmEyebrow, appConfirmModal, appConfirmSecondary, appConfirmTitle, appConfirmYes } from "../dom";
import { switchSection } from "../shell/nav";
import { escapeHtml } from "../utils/text";

export function closeAppConfirm() {
  if (appConfirmModal?.open) appConfirmModal.close();
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

    // showModal 负责焦点陷阱 / Esc / 背景 inert / 关闭后焦点还原，这里只管结果。
    // 每个出口都自己 settle，不把兑现挂在 close 事件上（Promise 二次 resolve 无副作用）。
    const settle = (value: boolean) => {
      appConfirmCancel?.removeEventListener("click", onCancel);
      appConfirmYes?.removeEventListener("click", onConfirm);
      appConfirmSecondary?.removeEventListener("click", onSecondaryClick);
      appConfirmModal?.removeEventListener("click", onBackdropClick);
      appConfirmModal?.removeEventListener("cancel", onDismiss);
      appConfirmModal?.removeEventListener("close", onDismiss);
      closeAppConfirm();
      resolve(value);
    };
    const onCancel = () => settle(false);
    const onConfirm = () => settle(true);
    const onSecondaryClick = () => {
      try {
        onSecondary?.();
      } catch {
        /* ignore */
      }
      settle(false);
    };
    // 点击 ::backdrop 时事件目标是 dialog 本身（面板在内层 div 上）
    const onBackdropClick = (event: MouseEvent) => {
      if (event.target === appConfirmModal) settle(false);
    };
    // Esc：cancel 先于 close，任一到达即当取消
    const onDismiss = () => settle(false);

    if (appConfirmEyebrow) appConfirmEyebrow.textContent = eyebrow;
    if (appConfirmTitle) appConfirmTitle.textContent = title;
    if (appConfirmDesc) {
      appConfirmDesc.hidden = !desc;
      appConfirmDesc.textContent = desc;
    }
    if (appConfirmBullets) {
      appConfirmBullets.hidden = !bullets.length;
      appConfirmBullets.innerHTML = bullets.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
    }
    appConfirmCancel.textContent = cancelLabel;
    appConfirmYes.textContent = confirmLabel;
    appConfirmYes.classList.toggle("btn-danger", Boolean(danger));
    if (appConfirmSecondary) {
      const showSecondary = Boolean(secondaryLabel);
      appConfirmSecondary.toggleAttribute("hidden", !showSecondary);
      appConfirmSecondary.textContent = showSecondary ? secondaryLabel : "";
    }

    appConfirmCancel.addEventListener("click", onCancel);
    appConfirmYes.addEventListener("click", onConfirm);
    if (secondaryLabel && appConfirmSecondary) {
      appConfirmSecondary.addEventListener("click", onSecondaryClick);
    }
    appConfirmModal.addEventListener("click", onBackdropClick);
    appConfirmModal.addEventListener("cancel", onDismiss);
    appConfirmModal.addEventListener("close", onDismiss);

    appConfirmModal.showModal();
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
