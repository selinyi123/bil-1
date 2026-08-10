/* eslint-disable */
/** Migrated from web/static/app.js — logic preserved. */

import { state } from "../state";
import { JOB_RESULT_HOVER_DISMISS_MS, jobResultBanner, jobResultClose, jobResultProgress } from "../dom";
import { hideParticipationResult, scheduleParticipationResultDismiss } from "../jobs/index";
import { prefersReducedMotion } from "../utils/motion";

export type ThemePreference = "light" | "dark" | "system";

const THEME_CYCLE: ThemePreference[] = ["light", "dark", "system"];

function getThemePreference(): ThemePreference {
  const stored = localStorage.getItem("binggo-theme");
  if (stored === "light" || stored === "dark" || stored === "system") return stored;
  return "system";
}

function systemPrefersDark(): boolean {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

/** 把偏好解析为实际主题：system 按系统配色解析。 */
export function resolveTheme(pref: ThemePreference): "dark" | "light" {
  return pref === "system" ? (systemPrefersDark() ? "dark" : "light") : pref;
}

export function initSystemPreferences() {
  applySidebarCollapsed(localStorage.getItem("binggo-sidebar-collapsed") === "1", { animate: false });
  applyTheme(getThemePreference(), { animate: false });
  document.getElementById("sidebar-collapse")?.addEventListener("click", () => {
    if (window.matchMedia("(max-width: 720px)").matches) return;
    const collapsed = !document.querySelector(".app-shell")?.classList.contains("sidebar-collapsed");
    applySidebarCollapsed(collapsed);
  });
  document.getElementById("theme-toggle")?.addEventListener("click", () => {
    const current = getThemePreference();
    const next = THEME_CYCLE[(THEME_CYCLE.indexOf(current) + 1) % THEME_CYCLE.length] ?? "system";
    applyTheme(next);
  });
  // 跟随系统：系统主题变化时自动切换（不写 localStorage）
  const systemMq = window.matchMedia("(prefers-color-scheme: dark)");
  const syncSystemTheme = () => {
    if (getThemePreference() === "system") applyTheme("system", { animate: false });
  };
  if (typeof systemMq.addEventListener === "function") {
    systemMq.addEventListener("change", syncSystemTheme);
  } else {
    systemMq.addListener(syncSystemTheme);
  }
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
    if (!jobResultBanner || jobResultBanner.hidden || jobResultBanner.classList.contains("is-hiding")) return;
    if (state.jobResultTimer) {
      window.clearTimeout(state.jobResultTimer);
      state.jobResultTimer = null;
    }
    if (jobResultProgress) jobResultProgress.style.animationPlayState = "paused";
  });
  jobResultBanner?.addEventListener("mouseleave", () => {
    if (!jobResultBanner || jobResultBanner.hidden || jobResultBanner.classList.contains("is-hiding")) return;
    if (jobResultProgress) jobResultProgress.style.animationPlayState = "running";
    scheduleParticipationResultDismiss(JOB_RESULT_HOVER_DISMISS_MS);
  });
}

export const SIDEBAR_ANIM_MS = 400;

export const THEME_ANIM_MS = 320;

interface SidebarShell extends HTMLElement {
  _sidebarAnimTimer?: number;
}

interface ThemeRoot extends HTMLElement {
  _themeAnimTimer?: number;
}

export function applySidebarCollapsed(collapsed: boolean, { animate = true } = {}) {
  const shell = document.querySelector<SidebarShell>(".app-shell");
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

export function applyTheme(theme: ThemePreference, { animate = true } = {}) {
  const next: ThemePreference = theme === "light" || theme === "dark" || theme === "system" ? theme : "system";
  const resolved: "dark" | "light" = resolveTheme(next);
  const current = getThemePreference();
  const run = () => {
    document.documentElement.dataset.theme = resolved;
    const btn = document.getElementById("theme-toggle");
    if (btn) {
      btn.classList.toggle("active", resolved === "dark");
      btn.classList.toggle("is-system-theme", next === "system");
      const text = btn.querySelector(".system-btn-text");
      const label = next === "system" ? "跟随系统" : resolved === "dark" ? "夜间模式" : "日间模式";
      if (text) text.textContent = label;
      btn.title = `主题：${label}（点击切换）`;
      btn.setAttribute("aria-label", `当前主题：${label}，点击切换到下一档`);
      btn.querySelector(".icon-moon")?.toggleAttribute("hidden", resolved === "dark");
      btn.querySelector(".icon-sun")?.toggleAttribute("hidden", resolved !== "dark");
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
  const rootEl = document.documentElement as ThemeRoot;
  window.clearTimeout(rootEl._themeAnimTimer);
  rootEl._themeAnimTimer = window.setTimeout(() => {
    document.documentElement.classList.remove("theme-animating");
  }, THEME_ANIM_MS);
}
