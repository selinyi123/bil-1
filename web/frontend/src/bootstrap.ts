/* eslint-disable */
/** Migrated from web/static/app.js — logic preserved. */

import { state } from "./state";
import type { JobStatus } from "./types";
import { bindOnboardingPanel, loadAccount, loadAccountExtras, logoutAccount, requestLogoutConfirm, syncProjectState } from "./account/index";
import { bindAddAccount } from "./account/add-account";
import { bindFilterPills, loadActivities, loadSummary } from "./activities/index";
import { bindAutoDock, fetchAutoStatus, setAutoDockOpen } from "./auto/index";
import { sidebarLogoutBtn, sidebarRefreshBtn } from "./dom";
import { bindActionButtons, setLogDockOpen, startPolling } from "./jobs/index";
import { startRealtime } from "./realtime/sse";
import { bindLlmApiKeyToggle, bindParticipateSettings, bindSettingsDirtyTracking, loadSettings, refreshLlmSettings, resetParticipateText, saveLlmSettings, saveParticipateText, testLlmSettings } from "./settings/index";
import { mountSettingsArchitecture } from "./settings/page";
import { mountDataSourceSettings } from "./sources/settings";
import { bindNavigation } from "./shell/nav";
import { initSystemPreferences } from "./shell/theme";
import { showToast } from "./shell/toast";
import { playOverviewEnter, setButtonLoading } from "./utils/motion";
import { sanitizeUserText } from "./utils/text";
import { bindDiagnosticsExport } from "./diagnostics/index";
import { bindCheckUpdates, loadRuntimeInfo } from "./runtime/index";
import { bindWatchUsers, loadWatchUsers } from "./watch/index";
import { mountExtraPanels, renderAccountPool } from "./extra/index";

function placeOperationalPanels(): void {
  const overview = document.getElementById("section-overview");
  if (!overview) return;
  const tools = document.querySelector<HTMLElement>(".extra-tools-panel");
  const logs = document.getElementById("extra-panel-logs");
  if (tools && tools.parentElement !== overview) overview.appendChild(tools);
  if (logs && logs.parentElement !== overview) overview.appendChild(logs);
}

export async function init() {
  initSystemPreferences();
  setLogDockOpen(false);
  setAutoDockOpen(false);

  // 信息架构必须先于 bindNavigation 创建：新增 Settings nav/section 才能进入统一导航绑定。
  mountSettingsArchitecture();
  mountDataSourceSettings();
  bindNavigation();
  bindAutoDock();
  window.addEventListener("binggo:auth-expired", () => {
    // 登录失效：刷新账号状态（loadAccount 自带未登录兜底渲染）
    loadAccount().catch(() => {});
  });
  bindFilterPills();
  bindParticipateSettings();
  bindSettingsDirtyTracking();
  bindLlmApiKeyToggle();
  bindWatchUsers();
  bindOnboardingPanel();
  bindActionButtons();
  bindAddAccount();
  bindDiagnosticsExport();
  bindCheckUpdates();
  loadRuntimeInfo().catch(() => {});

  // 配置类 Extra Panels（Enhance / Notify）跟随 participate-settings 进入 Settings；
  // 中奖深检 / Cleanup / 运行日志是操作工具，仍属于 Overview，不混入 Settings。
  await mountExtraPanels().catch(() => {});
  placeOperationalPanels();

  await syncProjectState();
  renderAccountPool().catch(() => {});
  try {
    const job = await loadSummary();
    if (job) state.currentJob = job as JobStatus;
    await fetchAutoStatus().catch(() => {});
    loadWatchUsers().catch(() => {});
    await loadActivities();
    startRealtime();
    if (job?.state === "running") startPolling();
  } catch (error) {
    const message = error instanceof Error ? error.message || error : String(error);
    showToast(sanitizeUserText(message) || "数据加载失败", "error");
  }
  playOverviewEnter();
}

document.getElementById("refresh-llm-settings")?.addEventListener("click", () => {
  refreshLlmSettings().catch(() => {});
});

document.getElementById("test-llm-settings")?.addEventListener("click", () => {
  testLlmSettings().catch(() => {});
});

document.getElementById("save-llm-settings")?.addEventListener("click", () => {
  saveLlmSettings().catch(() => {});
});

document.getElementById("save-participate-text")?.addEventListener("click", () => {
  saveParticipateText().catch(() => {});
});

document.getElementById("reset-participate-text")?.addEventListener("click", () => {
  resetParticipateText().catch(() => {});
});

sidebarRefreshBtn?.addEventListener("click", async () => {
  setButtonLoading(sidebarRefreshBtn, true, { label: "刷新中…" });
  try {
    const account = await loadAccount();
    const merged = (await loadAccountExtras()) || account;
    await loadSettings();
    await renderAccountPool().catch(() => {});
    if (!(merged as any)?.at_alert?.increased) {
      showToast("状态已同步", "success");
    }
  } catch (error) {
    showToast(String(error instanceof Error ? error.message || error : error), "error");
  } finally {
    setButtonLoading(sidebarRefreshBtn, false);
  }
});

sidebarLogoutBtn?.addEventListener("click", async () => {
  const confirmed = await requestLogoutConfirm();
  if (!confirmed) return;
  sidebarLogoutBtn!.disabled = true;
  try {
    await logoutAccount();
    // logout 会清空 active uid；账号池徽标、按 uid 的参与状态和三连候选也必须同步失效。
    await Promise.allSettled([renderAccountPool(), loadSummary(), loadActivities(), loadWatchUsers()]);
  } catch (error) {
    showToast(String(error instanceof Error ? error.message || error : error), "error");
  } finally {
    sidebarLogoutBtn!.disabled = false;
  }
});

window.addEventListener("pageshow", (event) => {
  if (!event.persisted) return;
  syncProjectState().catch((error) => {
    showToast(String(error instanceof Error ? error.message || error : error), "error");
  });
});
