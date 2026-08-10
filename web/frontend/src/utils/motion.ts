/* eslint-disable */
/** Migrated from web/static/app.js — logic preserved. */

import { filterResultSummary } from "../dom";

export function prefersReducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
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
  const row = document.querySelector<HTMLElement>(`.source-row[data-source-id="${CSS.escape(String(sourceId))}"]`);
  if (!row) return;
  row.classList.remove("is-flash");
  void row.offsetWidth;
  row.classList.add("is-flash");
  window.setTimeout(() => row.classList.remove("is-flash"), 1100);
}

export function pulseWatchSyncCard() {
  const card = document.querySelector<HTMLElement>(".watch-sync-card");
  if (!card || prefersReducedMotion()) return;
  card.classList.remove("is-sync-pulse");
  void card.offsetWidth;
  card.classList.add("is-sync-pulse");
  document.querySelectorAll<HTMLElement>(".watch-metric-value").forEach((el) => {
    el.classList.remove("is-value-pop");
    void el.offsetWidth;
    el.classList.add("is-value-pop");
  });
  window.setTimeout(() => {
    card.classList.remove("is-sync-pulse");
    document.querySelectorAll<HTMLElement>(".watch-metric-value").forEach((el) => el.classList.remove("is-value-pop"));
  }, 900);
}

export function playSourcesEnter() {
  const stack = document.querySelector<HTMLElement>("#section-sources .sources-stack");
  if (!stack || prefersReducedMotion()) return;
  stack.classList.remove("is-sources-entering");
  void stack.offsetWidth;
  stack.classList.add("is-sources-entering");
}

export function playActivitiesEnter() {
  const panel = document.querySelector<HTMLElement>("#section-activities .activities-panel");
  if (!panel || prefersReducedMotion()) return;
  panel.classList.remove("is-activities-entering");
  void panel.offsetWidth;
  panel.classList.add("is-activities-entering");
}

export function pulseFilterSummary() {
  if (!filterResultSummary || prefersReducedMotion()) return;
  filterResultSummary.classList.remove("is-updated");
  void filterResultSummary.offsetWidth;
  filterResultSummary.classList.add("is-updated");
}

export function flashFilterPill(button: HTMLElement | null) {
  if (!button || prefersReducedMotion()) return;
  button.classList.remove("is-just-selected");
  void button.offsetWidth;
  button.classList.add("is-just-selected");
  window.setTimeout(() => button.classList.remove("is-just-selected"), 520);
}

export function playActivityListEnter() {
  if (prefersReducedMotion()) return;
  const rows = document.querySelectorAll<HTMLElement>("#activities-body tr[data-dynamic-id], #activities-cards .activity-card");
  rows.forEach((el, index) => {
    el.classList.remove("is-row-entering");
    el.style.setProperty("--row-delay", `${Math.min(index, 12) * 28}ms`);
    void el.offsetWidth;
    el.classList.add("is-row-entering");
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
    el.classList.remove("is-value-pop");
    void el.offsetWidth;
    el.classList.add("is-value-pop");
    window.setTimeout(() => el.classList.remove("is-value-pop"), 420);
  };
  requestAnimationFrame(tick);
}

export function playOverviewEnter() {
  const stack = document.querySelector<HTMLElement>("#section-overview .overview-stack");
  if (!stack || prefersReducedMotion()) return;
  stack.classList.remove("is-overview-entering");
  void stack.offsetWidth;
  stack.classList.add("is-overview-entering");
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
