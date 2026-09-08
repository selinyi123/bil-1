/* eslint-disable */
/** Migrated from web/static/app.js — logic preserved. */

import { filterResultSummary } from "../dom";

export function prefersReducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** 重放一个 CSS 动画：移除类 → 强制重排 → 重新加类（可选到点自动移除）。 */
function replay(el: Element | null | undefined, className: string, removeAfterMs?: number) {
  if (!el) return;
  el.classList.remove(className);
  void (el as HTMLElement).offsetWidth;
  el.classList.add(className);
  if (removeAfterMs) {
    window.setTimeout(() => el.classList.remove(className), removeAfterMs);
  }
}

export function setButtonLoading(button: HTMLButtonElement | null, loading: boolean, options: { label?: string } = {}) {
  if (!button) return;
  const { label } = options;
  if (loading) {
    if (button.dataset.loadingActive !== "true") {
      button.dataset.loadingOriginalHtml = button.innerHTML;
      button.dataset.loadingActive = "true";
    }
    button.classList.add("is-loading");
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    const labelEl = button.querySelector(".triple-participate-btn-label");
    if (labelEl && label !== undefined) {
      labelEl.textContent = label;
    } else if (label !== undefined) {
      button.textContent = label;
    }
  } else {
    button.classList.remove("is-loading");
    button.removeAttribute("aria-busy");
    if (button.dataset.loadingActive === "true") {
      button.innerHTML = button.dataset.loadingOriginalHtml || button.innerHTML;
      delete button.dataset.loadingOriginalHtml;
      delete button.dataset.loadingActive;
    }
    button.disabled = false;
  }
}

export function clearActionButtonLoading() {
  document.querySelectorAll<HTMLButtonElement>("[data-action].is-loading, .triple-participate-btn.is-loading").forEach((btn) => {
    setButtonLoading(btn, false);
  });
  document.querySelectorAll(".source-row.is-updating").forEach((row) => {
    row.classList.remove("is-updating");
  });
}

export function setSourceRowUpdating(sourceId: string | number, updating: boolean) {
  if (!sourceId) return;
  const row = document.querySelector<HTMLElement>(`.source-row[data-source-id="${CSS.escape(String(sourceId))}"]`);
  if (!row) return;
  row.classList.toggle("is-updating", Boolean(updating));
}

export function flashSourceRow(sourceId: string | number) {
  if (!sourceId || prefersReducedMotion()) return;
  replay(document.querySelector(`.source-row[data-source-id="${CSS.escape(String(sourceId))}"]`), "is-flash", 1100);
}

export function pulseWatchSyncCard() {
  const card = document.querySelector<HTMLElement>(".watch-sync-card");
  if (!card || prefersReducedMotion()) return;
  replay(card, "is-sync-pulse", 900);
  document.querySelectorAll<HTMLElement>(".watch-metric-value").forEach((el) => replay(el, "is-value-pop", 900));
}

export function playSourcesEnter() {
  if (prefersReducedMotion()) return;
  replay(document.querySelector("#section-sources .sources-stack"), "is-sources-entering");
}

export function playActivitiesEnter() {
  if (prefersReducedMotion()) return;
  replay(document.querySelector("#section-activities .activities-panel"), "is-activities-entering");
}

export function pulseFilterSummary() {
  if (prefersReducedMotion()) return;
  replay(filterResultSummary, "is-updated");
}

export function flashFilterPill(button: HTMLElement | null) {
  if (prefersReducedMotion()) return;
  replay(button, "is-just-selected", 520);
}

export function playActivityListEnter() {
  if (prefersReducedMotion()) return;
  const rows = document.querySelectorAll<HTMLElement>("#activities-body tr[data-dynamic-id], #activities-cards .activity-card");
  rows.forEach((el, index) => {
    el.style.setProperty("--row-delay", `${Math.min(index, 12) * 28}ms`);
    replay(el, "is-row-entering");
  });
}

export function highlightWatchUserChip(mid: string | number) {
  if (!mid) return;
  const chip = document.querySelector(`[data-watch-mid="${CSS.escape(String(mid))}"]`);
  if (!chip || prefersReducedMotion()) return;
  chip.classList.add("is-new");
  window.setTimeout(() => chip.classList.remove("is-new"), 700);
}

export function flashButtonSuccess(button: HTMLButtonElement | null, label = "已保存") {
  if (!button || prefersReducedMotion()) return;
  const previousHtml = button.innerHTML;
  button.classList.add("is-save-success");
  button.textContent = label;
  window.setTimeout(() => {
    button.classList.remove("is-save-success");
    if (button.dataset.loadingActive === "true") return;
    button.innerHTML = previousHtml;
  }, 1100);
}

export function markSaveDirty(button: HTMLElement | null) {
  button?.classList.add("is-dirty");
}

export function clearSaveDirty(button: HTMLElement | null) {
  button?.classList.remove("is-dirty");
}

export function animateStatValue(el: HTMLElement | null, from: number | string, to: number | string) {
  if (!el) return;
  const startValue = Number(from) || 0;
  const endValue = Number(to) || 0;
  if (prefersReducedMotion() || startValue === endValue) {
    el.textContent = String(endValue);
    return;
  }
  const duration = 520;
  const startedAt = performance.now();
  el.classList.add("is-ticking");
  const tick = (now: number) => {
    const progress = Math.min(1, (now - startedAt) / duration);
    const eased = 1 - (1 - progress) ** 3;
    el.textContent = String(Math.round(startValue + (endValue - startValue) * eased));
    if (progress < 1) {
      requestAnimationFrame(tick);
      return;
    }
    el.textContent = String(endValue);
    el.classList.remove("is-ticking");
    replay(el, "is-value-pop", 420);
  };
  requestAnimationFrame(tick);
}

export function playOverviewEnter() {
  if (prefersReducedMotion()) return;
  replay(document.querySelector("#section-overview .overview-stack"), "is-overview-entering");
}

export function flashActivityRows(dynamicIds: Array<string | number>) {
  dynamicIds.forEach((dynamicId) => {
    if (!dynamicId) return;
    document.querySelectorAll(`[data-dynamic-id="${dynamicId}"]`).forEach((el) => {
      el.classList.add("row-flash");
      el.querySelector(".badge")?.classList.add("is-badge-pop");
      window.setTimeout(() => {
        el.classList.remove("row-flash");
        el.querySelector(".badge")?.classList.remove("is-badge-pop");
      }, 1800);
    });
  });
}
