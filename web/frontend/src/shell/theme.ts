// @ts-nocheck
/* eslint-disable */
/** Migrated from web/static/app.js — logic preserved. */

import { state } from "../state";
import { JOB_RESULT_HOVER_DISMISS_MS, jobResultBanner, jobResultClose, jobResultProgress } from "../dom";
import { hideParticipationResult, scheduleParticipationResultDismiss } from "../jobs/index";
import { prefersReducedMotion } from "../utils/motion";

export function initSystemPreferences() {
  applySidebarCollapsed(localStorage.getItem("binggo-sidebar-collapsed") === "1", { animate: false });
  applyTheme(localStorage.getItem("binggo-theme") === "dark" ? "dark" : "light", { animate: false });
  document.getElementById("sidebar-collapse")?.addEventListener("click", () => {
    if (window.matchMedia("(max-width: 720px)").matches) return;
    const collapsed = !document.querySelector(".app-shell")?.classList.contains("sidebar-collapsed");
    applySidebarCollapsed(collapsed);
  });
  document.getElementById("theme-toggle")?.addEventListener("click", () => {
    const isDark = document.documentElement.dataset.theme === "dark";
    applyTheme(isDark ? "light" : "dark");
  });
  const sidebarMobileMq = window.matchMedia("(max-width: 720px)");
  const syncSidebarViewport = () => {
    if (!sidebarMobileMq.matches) return;
    document.getElementById("sidebar")?.classList.remove("open");
  };
  if (typeof sidebarMobileMq.addEventListener === "function") {
    sidebarMobileMq.addEventListener("change", syncSidebarViewport);
  } else {
    sidebarMobileMq.addListener(syncSidebarViewport);
  }
  jobResultClose?.addEventListener("click", () => hideParticipationResult());
  jobResultBanner?.addEventListener("mouseenter", () => {
    if (jobResultBanner.hidden || jobResultBanner.classList.contains("is-hiding")) return;
    if (state.jobResultTimer) {
      window.clearTimeout(state.jobResultTimer);
      state.jobResultTimer = null;
    }
    if (jobResultProgress) jobResultProgress.style.animationPlayState = "paused";
  });
  jobResultBanner?.addEventListener("mouseleave", () => {
    if (jobResultBanner.hidden || jobResultBanner.classList.contains("is-hiding")) return;
    if (jobResultProgress) jobResultProgress.style.animationPlayState = "running";
    scheduleParticipationResultDismiss(JOB_RESULT_HOVER_DISMISS_MS);
  });
}

export const SIDEBAR_ANIM_MS = 400;

export const THEME_ANIM_MS = 320;

export function applySidebarCollapsed(collapsed, { animate = true } = {}) {
  const shell = document.querySelector(".app-shell");
  if (!shell) return;
  const isCollapsed = shell.classList.contains("sidebar-collapsed");
  if (isCollapsed === collapsed) {
    document.documentElement.classList.remove("sidebar-init-collapsed");
    return;
  }

  if (animate) {
    shell.classList.add("sidebar-animating");
    void shell.offsetWidth;
  }
  document.documentElement.classList.remove("sidebar-init-collapsed");
  shell.classList.toggle("sidebar-collapsed", collapsed);
  const btn = document.getElementById("sidebar-collapse");
  if (btn) {
    btn.classList.toggle("active", collapsed);
    btn.title = collapsed ? "展开侧边栏" : "收起侧边栏";
    btn.setAttribute("aria-expanded", collapsed ? "false" : "true");
    const text = btn.querySelector(".system-btn-text");
    if (text) text.textContent = collapsed ? "展开侧栏" : "靠边收起";
  }
  localStorage.setItem("binggo-sidebar-collapsed", collapsed ? "1" : "0");
  if (!animate) return;
  window.clearTimeout(shell._sidebarAnimTimer);
  shell._sidebarAnimTimer = window.setTimeout(() => {
    shell.classList.remove("sidebar-animating");
  }, SIDEBAR_ANIM_MS);
}

export function applyTheme(theme, { animate = true } = {}) {
  const next = theme === "dark" ? "dark" : "light";
  const current = document.documentElement.dataset.theme === "dark" ? "dark" : "light";
  const run = () => {
    document.documentElement.dataset.theme = next;
    const btn = document.getElementById("theme-toggle");
    if (btn) {
      btn.classList.toggle("active", next === "dark");
      const text = btn.querySelector(".system-btn-text");
      const label = next === "dark" ? "切换日间模式" : "切换夜间模式";
      if (text) text.textContent = next === "dark" ? "日间模式" : "夜间模式";
      btn.title = label;
      btn.setAttribute("aria-label", label);
      btn.querySelector(".icon-moon")?.toggleAttribute("hidden", next === "dark");
      btn.querySelector(".icon-sun")?.toggleAttribute("hidden", next !== "dark");
      if (animate && !prefersReducedMotion()) {
        btn.classList.remove("is-theme-flash");
        void btn.offsetWidth;
        btn.classList.add("is-theme-flash");
        window.setTimeout(() => btn.classList.remove("is-theme-flash"), 520);
      }
    }
    localStorage.setItem("binggo-theme", next);
  };

  if (!animate || current === next || prefersReducedMotion()) {
    run();
    return;
  }

  if (typeof document.startViewTransition === "function") {
    const transition = document.startViewTransition(run);
    transition.finished.catch(() => {});
    return;
  }

  document.documentElement.classList.add("theme-animating");
  run();
  window.clearTimeout(document.documentElement._themeAnimTimer);
  document.documentElement._themeAnimTimer = window.setTimeout(() => {
    document.documentElement.classList.remove("theme-animating");
  }, THEME_ANIM_MS);
}
