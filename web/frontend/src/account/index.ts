// @ts-nocheck
/* eslint-disable */
/** Migrated from web/static/app.js — logic preserved. */

import { state } from "../state";
import { fetchJSON } from "../api/client";
import { LLM_REQUIRED_ACTIONS, LOGIN_REQUIRED_ACTIONS, ONBOARDING_STEPS, ONBOARDING_STORAGE_KEY, accountHero, onboardingFootNote, onboardingPanel, onboardingPrimaryBtn, onboardingProgressFill, onboardingProgressLabel, onboardingSkipBtn, onboardingStepsEl, sidebarAccountCard, sidebarLoginBtn, sidebarLogoutBtn } from "../dom";
import { loadSettings } from "../settings/index";
import { closeAppConfirm, openAppConfirm } from "../shell/confirm";
import { switchSection } from "../shell/nav";
import { showToast } from "../shell/toast";
import { formatAccountStat } from "../utils/format";
import { prefersReducedMotion } from "../utils/motion";
import { escapeHtml, sanitizeUserText } from "../utils/text";
import { renderWatchUsersPanel, updateWatchUserFormState } from "../watch/index";

export function isLoggedIn() {
  return Boolean(state.account?.logged_in && !state.account?.expired);
}

export function isLlmConfigured() {
  return Boolean(state.settings?.llm?.configured);
}

export function isLlmTested() {
  return Boolean(state.settings?.llm?.test_passed);
}

export function isSetupComplete() {
  return isLoggedIn() && isLlmConfigured() && isLlmTested();
}

export function requireSetup(action) {
  if (action === "login") return true;
  if (!LOGIN_REQUIRED_ACTIONS.has(action)) return true;
  if (!isLoggedIn()) {
    showToast("请先扫码登录", "info", "登录后才能使用此功能");
    return false;
  }
  if (!LLM_REQUIRED_ACTIONS.has(action)) return true;
  if (!isLlmConfigured()) {
    showToast("请先配置 LLM", "info", "在概览页填写 API Key 与模型名称并保存");
    return false;
  }
  if (!isLlmTested()) {
    showToast("请先测试 LLM 连接", "info", "保存配置后点击「测试连接」，通过后才能使用项目功能");
    return false;
  }
  return true;
}

export function renderSetupChecklist() {
  const loggedIn = isLoggedIn();
  const llmOk = isLlmConfigured();
  const llmTested = isLlmTested();
  return `
    <div class="setup-checklist">
      <span class="setup-pill ${loggedIn ? "ok" : "warn"}"><span class="setup-pill-dot" aria-hidden="true"></span>账号${loggedIn ? "已登录" : "未登录"}</span>
      <span class="setup-pill ${llmOk ? "ok" : "warn"}"><span class="setup-pill-dot" aria-hidden="true"></span>LLM${llmOk ? "已配置" : "未配置"}</span>
      <span class="setup-pill ${llmTested ? "ok" : "warn"}"><span class="setup-pill-dot" aria-hidden="true"></span>连接${llmTested ? "已通过" : "未测试"}</span>
    </div>`;
}

export function getAccountHeroTone(account) {
  if (!account?.logged_in) {
    return account?.network_error && account?.cookie_saved ? "offline" : "warn";
  }
  if (isSetupComplete()) return "ready";
  return "warn";
}

export function renderAccountAvatar(account, { large = false } = {}) {
  const sizeClass = large ? " account-avatar-lg" : "";
  if (account?.face) {
    return `<img class="account-avatar${sizeClass}" src="${escapeHtml(account.face)}" alt="头像" referrerpolicy="no-referrer" crossorigin="anonymous" />`;
  }
  return `<div class="account-avatar account-avatar-fallback${sizeClass}"></div>`;
}

export function renderAccountAvatarWrap(account, { large = false } = {}) {
  const tone = getAccountHeroTone(account);
  const sizeClass = large ? " is-lg" : " is-sm";
  return `
    <div class="account-avatar-wrap${sizeClass} is-${tone}" data-tone="${tone}">
      ${renderAccountAvatar(account, { large })}
      <span class="account-status-dot" aria-hidden="true"></span>
    </div>`;
}

export function renderAccountStatusLabel(account) {
  if (isSetupComplete()) return "已就绪";
  if (account.expired) return "需重新扫码登录";
  if (!isLlmConfigured()) return "请完成 LLM 配置";
  if (!isLlmTested()) return "请完成 LLM 连接测试";
  return "请完成登录与配置";
}

export function isOnboardingDismissed() {
  try {
    return localStorage.getItem(ONBOARDING_STORAGE_KEY) === "done";
  } catch {
    return false;
  }
}

export function dismissOnboarding() {
  try {
    localStorage.setItem(ONBOARDING_STORAGE_KEY, "done");
  } catch {
    /* ignore */
  }
  state.onboardingCelebrating = false;
  renderOnboardingPanel();
}

export function getOnboardingCompletion() {
  return {
    login: isLoggedIn(),
    llm_save: isLlmConfigured(),
    llm_test: isLlmTested(),
    try: false,
  };
}

export function countOnboardingDone(completion) {
  let done = 0;
  if (completion.login) done += 1;
  if (completion.llm_save) done += 1;
  if (completion.llm_test) done += 1;
  return done;
}

export function getOnboardingCurrentIndex(completion) {
  if (!completion.login) return 0;
  if (!completion.llm_save) return 1;
  if (!completion.llm_test) return 2;
  return 3;
}

export function scrollToLlmSettings({ focusTest = false } = {}) {
  switchSection("overview");
  const panel = document.getElementById("llm-settings-panel");
  panel?.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "start" });
  window.setTimeout(() => {
    const target = document.getElementById(focusTest ? "test-llm-settings" : "llm-api-key-input");
    target?.focus({ preventScroll: true });
    panel?.classList.add("is-onboarding-focus");
    window.setTimeout(() => panel?.classList.remove("is-onboarding-focus"), 1600);
  }, prefersReducedMotion() ? 0 : 280);
}

export function runOnboardingStepAction(stepId) {
  if (stepId === "login") {
    sidebarLoginBtn?.click();
    return;
  }
  if (stepId === "llm_save") {
    scrollToLlmSettings({ focusTest: false });
    return;
  }
  if (stepId === "llm_test") {
    if (!isLlmConfigured()) {
      showToast("请先保存 LLM 配置", "info", "填写 API Key 与模型名称后点击「保存配置」");
      scrollToLlmSettings({ focusTest: false });
      return;
    }
    scrollToLlmSettings({ focusTest: true });
    return;
  }
  if (stepId === "try") {
    dismissOnboarding();
    switchSection("activities");
  }
}

export function renderOnboardingPanel() {
  if (!onboardingPanel) return;
  if (isOnboardingDismissed()) {
    onboardingPanel.hidden = true;
    return;
  }

  const completion = getOnboardingCompletion();
  const currentIndex = getOnboardingCurrentIndex(completion);
  const doneCount = countOnboardingDone(completion);
  const allCoreDone = completion.login && completion.llm_save && completion.llm_test;

  onboardingPanel.hidden = false;
  onboardingPanel.classList.toggle("is-complete", allCoreDone);
  onboardingPanel.classList.toggle("is-celebrating", Boolean(state.onboardingCelebrating));

  if (onboardingProgressFill) {
    onboardingProgressFill.style.width = `${Math.round((doneCount / ONBOARDING_STEPS.length) * 100)}%`;
  }
  if (onboardingProgressLabel) {
    onboardingProgressLabel.textContent = `${doneCount} / ${ONBOARDING_STEPS.length}`;
  }

  if (onboardingStepsEl) {
    onboardingStepsEl.innerHTML = ONBOARDING_STEPS.map((step, index) => {
      const stepDone =
        step.id === "login"
          ? completion.login
          : step.id === "llm_save"
            ? completion.llm_save
            : step.id === "llm_test"
              ? completion.llm_test
              : false;
      const isCurrent = index === currentIndex && !stepDone;
      const stateClass = stepDone ? "is-done" : isCurrent ? "is-current" : "is-pending";
      const marker = stepDone ? "✓" : String(index + 1);
      return `
        <li class="onboarding-step ${stateClass}" data-step-id="${step.id}">
          <div class="onboarding-step-marker" aria-hidden="true">${marker}</div>
          <div class="onboarding-step-copy">
            <p class="onboarding-step-title">${escapeHtml(step.title)}</p>
            <p class="onboarding-step-desc">${escapeHtml(step.desc)}</p>
          </div>
          <button type="button" class="btn btn-secondary btn-compact btn-pill onboarding-step-cta" data-onboarding-action="${step.id}" ${stepDone ? "disabled" : ""}>
            ${stepDone ? "已完成" : escapeHtml(step.cta)}
          </button>
        </li>`;
    }).join("");
  }

  if (onboardingFootNote) {
    if (state.onboardingCelebrating) {
      onboardingFootNote.textContent = "准备就绪！去活动页参与你的第一场抽奖吧。";
    } else if (allCoreDone) {
      onboardingFootNote.textContent = "登录与 LLM 已就绪，最后一步：去活动页试一次参与。";
    } else {
      onboardingFootNote.textContent = "按顺序完成每一步；可随时点击右侧按钮执行当前步骤。";
    }
  }

  if (onboardingPrimaryBtn) {
    const currentStep = ONBOARDING_STEPS[currentIndex];
    onboardingPrimaryBtn.hidden = false;
    if (allCoreDone) {
      onboardingPrimaryBtn.textContent = "完成引导";
    } else {
      onboardingPrimaryBtn.textContent = currentStep?.cta || "下一步";
    }
  }
}

export function bindOnboardingPanel() {
  onboardingSkipBtn?.addEventListener("click", () => dismissOnboarding());
  onboardingPrimaryBtn?.addEventListener("click", () => {
    const completion = getOnboardingCompletion();
    const currentIndex = getOnboardingCurrentIndex(completion);
    const step = ONBOARDING_STEPS[currentIndex];
    if (!step) return;
    if (step.id === "try" || (completion.login && completion.llm_save && completion.llm_test)) {
      state.onboardingCelebrating = true;
      renderOnboardingPanel();
      window.setTimeout(() => {
        dismissOnboarding();
        switchSection("activities");
      }, prefersReducedMotion() ? 0 : 520);
      return;
    }
    runOnboardingStepAction(step.id);
  });
  onboardingStepsEl?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-onboarding-action]");
    if (!button || button.disabled) return;
    runOnboardingStepAction(button.dataset.onboardingAction);
  });
}

export function renderAtAlertBanner(account) {
  const alert = account.at_alert;
  if (!alert?.increased) return "";
  const delta = Number(alert.delta) || Math.max(Number(alert.current) - Number(alert.previous), 0);
  const notifyUrl = account.at_notify_url || "https://message.bilibili.com/#/notify/at";
  return `
    <div class="account-at-alert" id="account-at-alert">
      <div class="account-at-alert-copy">
        <p class="account-at-alert-title">有新的 @ 通知</p>
        <p class="account-at-alert-desc">@我的 未读较上次增加了 ${delta} 条，建议登录 B 站消息中心查看是否中奖。</p>
      </div>
      <div class="account-at-alert-actions">
        <a class="btn btn-secondary btn-compact" href="${escapeHtml(notifyUrl)}" target="_blank" rel="noopener noreferrer">去 B 站查看</a>
        <button type="button" class="btn btn-primary btn-compact" id="account-at-ack-btn">知道了</button>
      </div>
    </div>`;
}

export function maybeShowAtUnreadAlert(account) {
  const alert = account?.at_alert;
  if (!alert?.increased) return;
  const key = `${alert.previous}->${alert.current}`;
  if (state.atAlertShownKey === key) return;
  state.atAlertShownKey = key;
  const delta = Number(alert.delta) || Math.max(Number(alert.current) - Number(alert.previous), 0);
  showToast(
    `@我的 未读增加了 ${delta} 条`,
    "info",
    "建议打开 B 站消息中心查看，中奖通知可能在此。"
  );
}

export async function acknowledgeAtUnread(current) {
  await fetchJSON("/api/account/ack-at-unread", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ current: Number(current) || 0 }),
    timeoutMs: 20000,
  });
  state.atAlertShownKey = "";
  return loadAccount();
}

export function bindAtAlertActions(account) {
  document.getElementById("account-at-ack-btn")?.addEventListener("click", async () => {
    try {
      await acknowledgeAtUnread(account.unread_at ?? 0);
      showToast("已记录当前 @ 未读数", "success");
    } catch (error) {
      showToast(String(error.message || error), "error");
    }
  });
}

export function renderAccountViews(account) {
  state.account = account;
  const loggedIn = Boolean(account.logged_in);

  if (sidebarLoginBtn) sidebarLoginBtn.hidden = loggedIn;
  if (sidebarLogoutBtn) sidebarLogoutBtn.hidden = !loggedIn;

  if (!loggedIn) {
    const networkError = Boolean(account.network_error);
    const cookieSaved = Boolean(account.cookie_saved);
    const title = networkError && cookieSaved ? "暂时无法连接 B 站" : "未登录";
    const subtitle = networkError && cookieSaved && account.mid
      ? `UID ${escapeHtml(account.mid)} · 本地 Cookie 已保存`
      : "";
    const tone = getAccountHeroTone(account);
    const emptyHtml = `
      <div class="account-empty">
        ${renderAccountAvatarWrap(account, { large: true })}
        <div>
          <h3>${escapeHtml(title)}</h3>
          ${subtitle ? `<p class="caption">${subtitle}</p>` : ""}
          <p>${escapeHtml(account.message || "请使用侧边栏扫码登录")}</p>
          ${renderSetupChecklist()}
          <span class="account-status warn">${networkError && cookieSaved ? "网络恢复后点击「刷新账号」" : "需完成登录、LLM 配置与连接测试"}</span>
        </div>
      </div>`;
    if (accountHero) {
      accountHero.classList.remove("is-ready", "is-warn", "is-offline");
      accountHero.classList.add(`is-${tone}`);
      accountHero.innerHTML = emptyHtml;
    }
    if (sidebarAccountCard) {
      const sidebarName = networkError && cookieSaved
        ? (account.uname || `UID ${account.mid || "—"}`)
        : "未登录";
      const sidebarSub = networkError && cookieSaved ? "网络异常" : "扫码登录后开始";
      sidebarAccountCard.innerHTML = `
        <div class="sidebar-account-mini is-${tone}" title="${escapeHtml(account.message || "请扫码登录")}">
          ${renderAccountAvatarWrap(account)}
          <div class="sidebar-account-text sidebar-fade">
            <p class="sidebar-account-name">${escapeHtml(sidebarName)}</p>
            <p class="sidebar-account-sub">${escapeHtml(sidebarSub)}</p>
          </div>
        </div>`;
    }
    updateWatchUserFormState();
    if (state.watchUsers) renderWatchUsersPanel(state.watchUsers);
    renderOnboardingPanel();
    return;
  }

  const tone = getAccountHeroTone(account);
  const ready = tone === "ready";
  const atNotifyUrl = account.at_notify_url || "https://message.bilibili.com/#/notify/at";
  const extrasLoading = Boolean(account.extras_loading);
  const atUnread = Number(formatAccountStat(account.unread_at, loggedIn, extrasLoading)) || 0;
  const heroHtml = `
    ${renderAccountAvatarWrap(account, { large: true })}
    <div class="account-hero-body">
      <p class="eyebrow">当前账号</p>
      <h2 class="account-hero-name">${escapeHtml(account.uname || "B站用户")}</h2>
      ${renderAtAlertBanner(account)}
      <div class="account-hero-stats">
        <div class="account-stat">
          <span class="account-stat-value">${account.following ?? "—"}</span>
          <span class="account-stat-label">关注</span>
        </div>
        <div class="account-stat">
          <span class="account-stat-value">${account.dynamic_count ?? "—"}</span>
          <span class="account-stat-label">动态</span>
        </div>
        <div class="account-stat">
          <span class="account-stat-value">${formatAccountStat(account.unread_messages, loggedIn, extrasLoading)}</span>
          <span class="account-stat-label">私信未读</span>
        </div>
        <div class="account-stat account-stat-at${atUnread > 0 ? " has-unread" : ""}">
          <span class="account-stat-value">${formatAccountStat(account.unread_at, loggedIn, extrasLoading)}</span>
          <span class="account-stat-label">
            <span>@我的</span>
            <a class="account-stat-inline-link" href="${escapeHtml(atNotifyUrl)}" target="_blank" rel="noopener noreferrer" title="在 B 站查看 @ 我的通知">查看</a>
          </span>
        </div>
      </div>
      <div class="account-hero-footer">
        ${renderSetupChecklist()}
        <span class="account-status ${ready ? "ok" : "warn"}">${escapeHtml(renderAccountStatusLabel(account))}</span>
      </div>
    </div>`;
  if (accountHero) {
    accountHero.classList.remove("is-ready", "is-warn", "is-offline");
    accountHero.classList.add(`is-${tone}`);
    accountHero.innerHTML = heroHtml;
  }
  bindAtAlertActions(account);

  if (sidebarAccountCard) {
    sidebarAccountCard.innerHTML = `
      <div class="sidebar-account-mini is-${tone}" title="${escapeHtml(account.uname || "B站用户")}">
        ${renderAccountAvatarWrap(account)}
        <div class="sidebar-account-text sidebar-fade">
          <p class="sidebar-account-name">${escapeHtml(account.uname || "B站用户")}</p>
          <p class="sidebar-account-sub">UID ${escapeHtml(account.mid || "—")}</p>
        </div>
      </div>`;
  }
  updateWatchUserFormState();
  if (state.watchUsers) renderWatchUsersPanel(state.watchUsers);
  renderOnboardingPanel();
}

export async function loadAccount() {
  try {
    const account = await fetchJSON("/api/account", { timeoutMs: 12000 });
    renderAccountViews(account);
    return account;
  } catch (error) {
    const message = sanitizeUserText(error.message || error) || "账号信息加载失败，请稍后重试";
    const account = {
      logged_in: false,
      expired: true,
      message,
      uname: "",
      face: "",
      mid: null,
      following: null,
      dynamic_count: null,
      unread_messages: null,
      unread_at: null,
      extras_loading: false,
    };
    renderAccountViews(account);
    return account;
  }
}

export async function loadAccountExtras() {
  if (!state.account?.logged_in) return null;
  try {
    const extras = await fetchJSON("/api/account/extras", { timeoutMs: 15000 });
    const merged = { ...state.account, ...extras };
    renderAccountViews(merged);
    maybeShowAtUnreadAlert(merged);
    return merged;
  } catch {
    if (state.account?.logged_in) {
      renderAccountViews({ ...state.account, extras_loading: false });
    }
    return null;
  }
}

export async function logoutAccount() {
  // 与 fetchJSON 对齐：解析契约错误，避免把整段 JSON 丢给 toast
  await fetchJSON("/api/logout", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  try {
    await loadAccount();
  } catch (error) {
    renderAccountViews({
      logged_in: false,
      expired: true,
      message: "请重新扫码登录",
      uname: "",
      face: "",
      mid: null,
      following: null,
      dynamic_count: null,
      unread_messages: null,
      unread_at: null,
    });
  }
  showToast("已退出登录", "success", "本地 Cookie 已清除，请重新扫码登录");
}

export function closeLogoutConfirmModal() {
  closeAppConfirm();
}

export function requestLogoutConfirm() {
  return openAppConfirm({
    eyebrow: "账号",
    title: "确认退出登录？",
    desc: "退出后将清除本地登录状态，需要重新扫码登录才能继续使用参与、刷新等功能。",
    confirmLabel: "确认退出",
    cancelLabel: "取消",
  });
}

export async function syncProjectState() {
  const account = await loadAccount();
  loadAccountExtras().catch(() => null);
  try {
    await loadSettings();
  } catch (error) {
    showToast(sanitizeUserText(error.message || error) || "设置加载失败", "error");
  }
  if (state.account) renderAccountViews(state.account);
  return account;
}
