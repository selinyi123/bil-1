// @ts-nocheck
/* eslint-disable */
/** Migrated from web/static/app.js — logic preserved. */

import { logDockToggle, qrcodeModal } from "../dom";
import { hideQrcodeModal, toggleLogDock, trapQrcodeFocus } from "../jobs/index";
import { playActivitiesEnter, playOverviewEnter, playSourcesEnter, prefersReducedMotion } from "../utils/motion";
import { loadWatchUsers } from "../watch/index";

let sectionSwitchTimer = null;

export function activateSection(sectionId) {
  const target = document.getElementById(`section-${sectionId}`);
  document.querySelectorAll(".nav-item").forEach((item) => {
    const active = item.dataset.section === sectionId;
    item.classList.toggle("active", active);
    if (active && !prefersReducedMotion()) {
      item.classList.remove("is-nav-flash");
      void item.offsetWidth;
      item.classList.add("is-nav-flash");
      window.setTimeout(() => item.classList.remove("is-nav-flash"), 480);
    }
  });
  document.querySelectorAll(".view-section").forEach((section) => {
    const active = section === target;
    section.classList.remove("is-leaving");
    section.classList.toggle("active", active);
    if (active) {
      section.classList.remove("is-entering");
      void section.offsetWidth;
      if (!prefersReducedMotion()) {
        section.classList.add("is-entering");
      }
      document.getElementById("page-title").textContent = section.dataset.title || sectionId;
      document.getElementById("page-subtitle").textContent = section.dataset.subtitle || "";
      if (sectionId === "overview") playOverviewEnter();
      if (sectionId === "sources") playSourcesEnter();
      if (sectionId === "activities") playActivitiesEnter();
    }
  });
  document.getElementById("sidebar")?.classList.remove("open");
  if (sectionId === "sources") {
    loadWatchUsers().catch(() => {});
  }
}

export function switchSection(sectionId) {
  const target = document.getElementById(`section-${sectionId}`);
  const current = document.querySelector(".view-section.active");
  if (!target || current === target) return;

  if (sectionSwitchTimer) {
    window.clearTimeout(sectionSwitchTimer);
    sectionSwitchTimer = null;
  }

  if (!prefersReducedMotion() && current) {
    current.classList.add("is-leaving");
    current.classList.remove("is-entering");
    sectionSwitchTimer = window.setTimeout(() => {
      current.classList.remove("active", "is-leaving", "is-entering");
      activateSection(sectionId);
      sectionSwitchTimer = null;
    }, 220);
    return;
  }

  if (current) {
    current.classList.remove("active", "is-leaving", "is-entering");
  }
  activateSection(sectionId);
}

export function bindNavigation() {
  document.querySelectorAll("[data-section]").forEach((button) => {
    button.addEventListener("click", () => switchSection(button.dataset.section));
  });
  document.querySelectorAll("[data-section-jump]").forEach((button) => {
    button.addEventListener("click", () => switchSection(button.dataset.sectionJump));
  });
  document.getElementById("sidebar-toggle")?.addEventListener("click", () => {
    document.getElementById("sidebar")?.classList.toggle("open");
  });
  logDockToggle?.addEventListener("click", () => toggleLogDock(true));
  document.getElementById("log-dock-collapse")?.addEventListener("click", () => toggleLogDock(false));
  document.getElementById("qrcode-close")?.addEventListener("click", () => hideQrcodeModal(true));
  document.getElementById("qrcode-backdrop")?.addEventListener("click", () => hideQrcodeModal(true));
  document.addEventListener("keydown", (event) => {
    trapQrcodeFocus(event);
    if (event.key === "Escape" && qrcodeModal && !qrcodeModal.hidden) {
      hideQrcodeModal(true);
    }
  });
}
