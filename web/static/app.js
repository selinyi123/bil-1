const state = {
  page: 1,
  pageSize: 30,
  filters: { q: "", type: "", status: "", draw: "active" },
  polling: null,
  logDockOpen: false,
  qrcodeDismissed: false,
  lastQrcodeRefresh: 0,
  account: null,
  settings: null,
};

const jobMessage = document.getElementById("job-message");
const jobLog = document.getElementById("job-log");
const statsGrid = document.getElementById("stats-grid");
const sourceGrid = document.getElementById("source-grid");
const accountHero = document.getElementById("account-hero");
const sidebarAccountCard = document.getElementById("sidebar-account-card");
const sidebarLoginBtn = document.getElementById("sidebar-login");
const sidebarLogoutBtn = document.getElementById("sidebar-logout");
const sidebarRefreshBtn = document.getElementById("sidebar-refresh-account");
const activitiesBody = document.getElementById("activities-body");
const pagination = document.getElementById("pagination");
const qrcodeModal = document.getElementById("qrcode-modal");
const qrcodeImg = document.getElementById("qrcode-img");
const qrcodeStatus = document.getElementById("qrcode-status");
const progressBanner = document.getElementById("progress-banner");
const progressLabel = document.getElementById("progress-label");
const progressDetail = document.getElementById("progress-detail");
const progressFill = document.getElementById("progress-fill");
const progressSteps = document.getElementById("progress-steps");
const toastStack = document.getElementById("toast-stack");
const logDock = document.getElementById("log-dock");
const logDockPanel = document.getElementById("log-dock-panel");
const logDockToggle = document.getElementById("log-dock-toggle");
const logDockBadge = document.getElementById("log-dock-badge");

const PARTICIPATE_STEP_LABELS = ["点赞", "关注", "收藏", "转发", "评论"];
const ACTION_LABELS = {
  like: "点赞",
  follow: "关注",
  favorite: "收藏",
  repost: "转发",
  comment: "评论",
  reserve: "预约",
};
const LOGIN_REQUIRED_ACTIONS = new Set(["refresh_all", "participate"]);

function isLoggedIn() {
  return Boolean(state.account?.logged_in && !state.account?.expired);
}

function isLlmConfigured() {
  return Boolean(state.settings?.llm?.configured);
}

function isSetupComplete() {
  return isLoggedIn() && isLlmConfigured();
}

function requireSetup(action) {
  if (action === "login") return true;
  if (!LOGIN_REQUIRED_ACTIONS.has(action)) return true;
  if (!isLoggedIn()) {
    showToast("请先扫码登录", "info", "完成登录与 LLM 配置后才能使用项目功能");
    return false;
  }
  if (!isLlmConfigured()) {
    showToast("请先配置 LLM", "info", "在概览页填写 API Key、接口地址与模型名并保存");
    return false;
  }
  return true;
}

function renderSetupChecklist() {
  const loggedIn = isLoggedIn();
  const llmOk = isLlmConfigured();
  return `
    <div class="setup-checklist">
      <span class="setup-pill ${loggedIn ? "ok" : "warn"}">① 账号${loggedIn ? "已登录" : "未登录"}</span>
      <span class="setup-pill ${llmOk ? "ok" : "warn"}">② LLM${llmOk ? "已配置" : "未配置"}</span>
      ${isSetupComplete() ? '<span class="setup-pill ready">可以开始使用</span>' : ""}
    </div>`;
}

function sanitizeUserText(text) {
  const raw = String(text || "").trim();
  if (!raw) return "";
  if (/traceback|nameerror|\.py\b|line \d+/i.test(raw)) {
    return "任务执行时发生内部错误，请稍后重试";
  }
  return raw
    .replace(/[A-Za-z]:\\[^\s"']+/g, "[本地文件]")
    .replace(/→\s*\S+/g, "→ 已保存");
}

function formatToastDetail(job) {
  if (!job?.log) return "";
  const lines = sanitizeUserText(job.log)
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .slice(0, 3);
  return lines.join(" · ");
}

const TOAST_META = {
  success: { title: "执行成功", icon: "✓" },
  error: { title: "执行失败", icon: "!" },
  info: { title: "提示", icon: "i" },
  running: { title: "执行中", icon: "…" },
};

function formatLastParticipation(last) {
  if (!last) return "";
  const status = last.status || "";
  const message = last.message || "";
  if (status === "joined") return message || "参与成功";
  if (status === "failed") {
    const failed = (last.actions || []).filter((item) => item && item.ok === false);
    if (failed.length) {
      const labels = failed.map((item) => ACTION_LABELS[item.action] || item.action).join("、");
      return `失败：${labels}${message ? `（${message}）` : ""}`;
    }
    return message || "参与失败";
  }
  return message || status;
}

function badgeClass(status) {
  if (status === "已参加") return "badge joined";
  return "badge pending";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function fetchJSON(url, options = {}) {
  const { timeoutMs = 30000, ...fetchOptions } = options;
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { ...fetchOptions, signal: controller.signal });
    if (!response.ok) {
      const text = await response.text();
      let message = text || response.statusText;
      try {
        const payload = JSON.parse(text);
        if (payload?.detail) message = String(payload.detail);
      } catch {
        // 非 JSON 响应，保留原始文本
      }
      throw new Error(message);
    }
    return response.json();
  } catch (error) {
    if (error.name === "AbortError") throw new Error("请求超时，请稍后重试");
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}

function showToast(message, type = "info", detail = "") {
  if (!toastStack || !message) return;
  const meta = TOAST_META[type] || TOAST_META.info;
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <div class="toast-icon" aria-hidden="true">${meta.icon}</div>
    <div class="toast-body">
      <p class="toast-title">${escapeHtml(meta.title)}</p>
      <p class="toast-message">${escapeHtml(message)}</p>
      ${detail ? `<p class="toast-detail">${escapeHtml(detail)}</p>` : ""}
    </div>
    <button type="button" class="toast-close" aria-label="关闭">×</button>
    <div class="toast-progress" aria-hidden="true"></div>`;
  const duration = type === "error" ? 6000 : type === "running" ? 2400 : 4200;
  const progress = toast.querySelector(".toast-progress");
  progress.style.animationDuration = `${duration}ms`;
  toast.querySelector(".toast-close")?.addEventListener("click", () => toast.remove());
  toastStack.appendChild(toast);
  window.setTimeout(() => {
    toast.classList.add("toast-hide");
    window.setTimeout(() => toast.remove(), 320);
  }, duration);
}

function showQrcodeModal() {
  if (!qrcodeModal || state.qrcodeDismissed) return;
  qrcodeModal.hidden = false;
  document.body.classList.add("modal-open");
  if (qrcodeStatus) qrcodeStatus.textContent = "等待扫码…";
  if (qrcodeImg) qrcodeImg.src = `/api/login/qrcode?t=${Date.now()}`;
}

function hideQrcodeModal(manual = false) {
  if (!qrcodeModal) return;
  if (manual) {
    state.qrcodeDismissed = true;
    cancelLoginJob();
  }
  qrcodeModal.hidden = true;
  document.body.classList.remove("modal-open");
}

async function cancelLoginJob() {
  try {
    const job = await fetchJSON("/api/jobs/current");
    if (job.state === "running" && job.action === "login") {
      await fetchJSON("/api/jobs/cancel", { method: "POST" });
      if (state.polling) {
        window.clearInterval(state.polling);
        state.polling = null;
      }
      setButtonsDisabled(false);
      updateJobUI({ state: "idle", message: "已取消扫码登录", log: "登录流程已结束" });
      showToast("已取消扫码登录", "info");
    }
  } catch (error) {
    showToast(sanitizeUserText(error.message || error), "error");
  }
}

function setLogDockOpen(open) {
  state.logDockOpen = open;
  if (!logDockPanel || !logDockToggle) return;
  logDockPanel.hidden = !open;
  logDockToggle.hidden = open;
  logDockToggle.setAttribute("aria-expanded", String(open));
  logDock?.classList.toggle("open", open);
}

function toggleLogDock(forceOpen) {
  const next = typeof forceOpen === "boolean" ? forceOpen : !state.logDockOpen;
  setLogDockOpen(next);
}

function renderParticipateSteps(job) {
  if (!progressSteps) return;
  if (job.state !== "running" || job.action !== "participate") {
    progressSteps.hidden = true;
    progressSteps.innerHTML = "";
    return;
  }
  const total = Number(job.progress_total) || PARTICIPATE_STEP_LABELS.length;
  const current = Number(job.progress_step) || 0;
  const labels = total === 1 ? ["预约"] : PARTICIPATE_STEP_LABELS.slice(0, total);
  progressSteps.hidden = false;
  progressSteps.innerHTML = labels
    .map((label, index) => {
      const stepNo = index + 1;
      let stepState = "pending";
      if (current > stepNo) stepState = "done";
      else if (current === stepNo) stepState = "active";
      return `<li class="progress-step ${stepState}"><span>${label}</span></li>`;
    })
    .join("");
}

function setButtonsDisabled(disabled) {
  document.querySelectorAll("[data-action]").forEach((button) => {
    button.disabled = disabled;
  });
}

function renderStats(summary) {
  const counts = summary.user_status_counts || {};
  const drawCounts = summary.counts || {};
  const cards = [
    { label: "活动总数", value: summary.total_count || 0 },
    { label: "未参加", value: counts["未参加"] || 0 },
    { label: "已参加", value: counts["已参加"] || 0 },
    { label: "进行中", value: drawCounts.active || 0 },
    { label: "新增链接", value: summary.new_count || 0 },
  ];
  statsGrid.innerHTML = cards
    .map(
      (card) => `
      <article class="stat-card">
        <p class="stat-label">${card.label}</p>
        <p class="stat-value">${card.value}</p>
      </article>`
    )
    .join("");
}

function renderAccountViews(account) {
  state.account = account;
  const loggedIn = Boolean(account.logged_in);

  if (sidebarLoginBtn) sidebarLoginBtn.hidden = loggedIn;
  if (sidebarLogoutBtn) sidebarLogoutBtn.hidden = !loggedIn;

  if (!loggedIn) {
    const emptyHtml = `
      <div class="account-empty">
        <div class="account-avatar account-avatar-fallback account-avatar-lg"></div>
        <div>
          <h3>未登录</h3>
          <p>${escapeHtml(account.message || "请使用侧边栏扫码登录")}</p>
          ${renderSetupChecklist()}
          <span class="account-status warn">需完成登录与 LLM 配置</span>
        </div>
      </div>`;
    if (accountHero) accountHero.innerHTML = emptyHtml;
    if (sidebarAccountCard) {
      sidebarAccountCard.innerHTML = `
        <div class="sidebar-account-mini">
          <div class="account-avatar account-avatar-fallback"></div>
          <div>
            <p class="sidebar-account-name">未登录</p>
            <p class="sidebar-account-sub">扫码登录后开始</p>
          </div>
        </div>`;
    }
    return;
  }

  const avatar = account.face
    ? `<img class="account-avatar account-avatar-lg" src="${escapeHtml(account.face)}" alt="头像" referrerpolicy="no-referrer" crossorigin="anonymous" />`
    : `<div class="account-avatar account-avatar-fallback account-avatar-lg"></div>`;
  const heroHtml = `
    ${avatar}
    <div class="account-hero-body">
      <p class="eyebrow">当前账号</p>
      <h2 class="account-hero-name">${escapeHtml(account.uname || "B站用户")}</h2>
      <div class="account-hero-stats">
        <div class="account-stat"><span class="account-stat-value">${account.following ?? "—"}</span><span class="account-stat-label">关注</span></div>
        <div class="account-stat"><span class="account-stat-value">${account.dynamic_count ?? "—"}</span><span class="account-stat-label">动态</span></div>
        <div class="account-stat"><span class="account-stat-value">${account.unread_messages ?? "—"}</span><span class="account-stat-label">私信未读</span></div>
      </div>
      ${renderSetupChecklist()}
      <span class="account-status ${isSetupComplete() ? "ok" : "warn"}">${isSetupComplete() ? "已就绪" : account.expired ? "需重新扫码登录" : "请完成 LLM 配置"}</span>
    </div>`;
  if (accountHero) accountHero.innerHTML = heroHtml;

  const sidebarAvatar = account.face
    ? `<img class="account-avatar" src="${escapeHtml(account.face)}" alt="头像" referrerpolicy="no-referrer" crossorigin="anonymous" />`
    : `<div class="account-avatar account-avatar-fallback"></div>`;
  if (sidebarAccountCard) {
    sidebarAccountCard.innerHTML = `
      <div class="sidebar-account-mini">
        ${sidebarAvatar}
        <div>
          <p class="sidebar-account-name">${escapeHtml(account.uname || "B站用户")}</p>
          <p class="sidebar-account-sub">UID ${escapeHtml(account.mid || "—")}</p>
        </div>
      </div>`;
  }
}

async function loadAccount() {
  const account = await fetchJSON("/api/account", { timeoutMs: 20000 });
  renderAccountViews(account);
  return account;
}

async function logoutAccount() {
  const response = await fetch("/api/logout", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "退出登录失败");
  }
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
    });
  }
  showToast("已退出登录", "success", "本地 Cookie 已清除，请重新扫码登录");
}

async function loadSettings() {
  const settings = await fetchJSON("/api/settings");
  state.settings = settings;
  const input = document.getElementById("participate-text-input");
  if (input) input.value = settings.participate_text || settings.default_participate_text || "好运连连！";
  renderLlmSettingsForm(settings);
  if (state.account?.logged_in) renderAccountViews(state.account);
  return settings;
}

function renderLlmSettingsForm(settings) {
  const llm = settings?.llm || {};
  const defaults = settings?.llm_defaults || {};
  const baseInput = document.getElementById("llm-base-url-input");
  const modelInput = document.getElementById("llm-model-name-input");
  const keyInput = document.getElementById("llm-api-key-input");
  const keyHint = document.getElementById("llm-api-key-hint");
  const status = document.getElementById("llm-settings-status");
  if (baseInput) baseInput.value = llm.base_url_customized ? llm.base_url || "" : "";
  if (modelInput) modelInput.value = llm.model_name || defaults.model_name || "";
  if (keyInput) {
    keyInput.value = "";
    keyInput.placeholder = llm.configured ? "已配置，留空则不修改" : "请输入 API Key";
  }
  if (keyHint) {
    keyHint.textContent = llm.configured
      ? `当前 Key：${llm.api_key_hint || "****"}（输入新 Key 可覆盖）`
      : "尚未保存 API Key";
  }
  if (status) {
    if (!isLoggedIn()) status.textContent = "需先登录，再保存 LLM 配置";
    else if (llm.configured) status.textContent = "LLM 已配置，保存后立即生效";
    else status.textContent = "请填写 API Key 并保存，完成后才能使用项目功能";
  }
}

async function saveLlmSettings() {
  if (!isLoggedIn()) {
    showToast("请先扫码登录", "info", "登录后才能配置 LLM");
    return;
  }
  const result = await fetchJSON("/api/settings/llm", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      api_key: document.getElementById("llm-api-key-input")?.value || "",
      base_url: document.getElementById("llm-base-url-input")?.value || "",
      model_name: document.getElementById("llm-model-name-input")?.value || "",
    }),
  });
  state.settings = { ...(state.settings || {}), llm: result.llm, setup_complete: result.setup_complete };
  renderLlmSettingsForm(state.settings);
  if (state.account?.logged_in) renderAccountViews(state.account);
  showToast("LLM 配置已保存", "success", `${result.llm.model_name} · ${result.llm.api_key_hint || "已配置"}`);
}

async function resetLlmSettings() {
  if (!isLoggedIn()) {
    showToast("请先扫码登录", "info", "登录后才能配置 LLM");
    return;
  }
  const defaults = state.settings?.llm_defaults || {};
  const baseInput = document.getElementById("llm-base-url-input");
  const modelInput = document.getElementById("llm-model-name-input");
  if (baseInput) baseInput.value = "";
  if (modelInput) modelInput.value = defaults.model_name || "DeepSeek-V4-Flash";
  showToast("已恢复默认模型", "info", "接口地址已清空，使用内置默认");
}

async function saveParticipateText() {
  if (!isLoggedIn()) {
    showToast("请先扫码登录", "info", "登录后才能修改参与文案");
    return;
  }
  const input = document.getElementById("participate-text-input");
  const value = input?.value?.trim() || "";
  const result = await fetchJSON("/api/settings/participate-text", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ participate_text: value }),
  });
  if (input) input.value = result.participate_text;
  showToast("参与文案已保存", "success", result.participate_text);
}

async function resetParticipateText() {
  if (!isLoggedIn()) {
    showToast("请先扫码登录", "info", "登录后才能修改参与文案");
    return;
  }
  const result = await fetchJSON("/api/settings/participate-text", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ participate_text: "好运连连！" }),
  });
  const input = document.getElementById("participate-text-input");
  if (input) input.value = result.participate_text;
  showToast("已恢复默认文案", "success", result.participate_text);
}

function renderSources(sources) {
  sourceGrid.innerHTML = (sources || [])
    .map((source, index) => {
      const links = [];
      if (source.space_url) {
        links.push(`<a class="source-link" href="${escapeHtml(source.space_url)}" target="_blank" rel="noopener">UP 主页</a>`);
      }
      if (source.container_url) {
        links.push(`<a class="source-link" href="${escapeHtml(source.container_url)}" target="_blank" rel="noopener">当前合集</a>`);
      }
      const statusClass = source.updated ? "fresh" : "cached";
      const statusText = source.updated ? "本次有更新" : "使用缓存";
      return `
      <article class="source-row" style="--row-delay:${index * 40}ms">
        <div class="source-row-index">${escapeHtml(source.id)}</div>
        <div class="source-row-body">
          <div class="source-row-head">
            <h3>${escapeHtml(source.name)}</h3>
            <span class="source-status ${statusClass}">${statusText}</span>
          </div>
          <p class="source-row-meta">${source.link_count} 条链接 · ${escapeHtml(source.title || "暂无标题")}</p>
          <p class="source-row-time">最近检查：${escapeHtml(source.checked_at_text || "尚未更新")}</p>
          <div class="source-links">${links.join("") || '<span class="caption">暂无外链</span>'}</div>
        </div>
      </article>`;
    })
    .join("");
}

function renderActivities(payload) {
  const items = payload.items || [];
  if (!items.length) {
    activitiesBody.innerHTML = `<tr class="empty-row"><td colspan="6">没有匹配的活动</td></tr>`;
  } else {
    activitiesBody.innerHTML = items
      .map((item) => {
        const participateBtn = item.can_participate
          ? `<button class="btn btn-primary btn-compact btn-pill" data-action="participate" data-dynamic-id="${escapeHtml(item.dynamic_id)}">参与</button>`
          : `<span class="caption">—</span>`;
        const lastNote = item.last_participation
          ? `<div class="last-result ${escapeHtml(item.last_participation.status || "")}">上次：${escapeHtml(formatLastParticipation(item.last_participation))}</div>`
          : "";
        const linkCell = item.source_url
          ? `<a class="activity-link" href="${escapeHtml(item.source_url)}" target="_blank" rel="noopener">打开动态</a>`
          : `<span class="caption">—</span>`;
        return `
          <tr>
            <td class="activity-cell">
              <div class="activity-title">${escapeHtml(item.activity_title || item.prize || "未知活动")}</div>
              ${lastNote}
            </td>
            <td class="link-cell">${linkCell}</td>
            <td class="chip-cell"><span class="type-chip">${escapeHtml(item.lottery_type)}</span></td>
            <td class="chip-cell"><span class="${badgeClass(item.activity_status)}">${escapeHtml(item.activity_status)}</span></td>
            <td class="time-cell"><span class="time-pill">${escapeHtml(item.lottery_time || "—")}</span></td>
            <td class="chip-cell">${participateBtn}</td>
          </tr>`;
      })
      .join("");
  }

  pagination.innerHTML = `
    <span class="caption">第 ${payload.page} / ${payload.pages} 页，共 ${payload.total} 条</span>
    <div class="action-row">
      <button class="btn btn-secondary btn-compact" id="page-prev" ${payload.page <= 1 ? "disabled" : ""}>上一页</button>
      <button class="btn btn-secondary btn-compact" id="page-next" ${payload.page >= payload.pages ? "disabled" : ""}>下一页</button>
    </div>`;

  document.getElementById("page-prev")?.addEventListener("click", () => {
    state.page = Math.max(1, state.page - 1);
    loadActivities();
  });
  document.getElementById("page-next")?.addEventListener("click", () => {
    state.page += 1;
    loadActivities();
  });
  bindActionButtons();
}

function updateProgressUI(job) {
  const running = job.state === "running";
  progressBanner.hidden = !running;
  if (!running) {
    progressFill.style.width = "0%";
    renderParticipateSteps(job);
    return;
  }
  const total = Number(job.progress_total) || 0;
  const step = Number(job.progress_step) || 0;
  const percent = total > 0 ? Math.min(100, Math.round((step / total) * 100)) : 12;
  progressFill.style.width = `${percent}%`;
  progressLabel.textContent = job.label || "任务运行中…";
  progressDetail.textContent = job.progress_message || job.message || "请稍候，任务在后台执行中";
  renderParticipateSteps(job);
}

function updateJobUI(job) {
  jobMessage.textContent = sanitizeUserText(job.message) || "暂无任务";
  jobLog.textContent = sanitizeUserText(job.log) || "";
  if (logDockBadge) {
    const running = job.state === "running";
    logDockBadge.hidden = !running;
    logDockBadge.textContent = running ? "运行中" : "";
  }
  if (job.state === "running") toggleLogDock(true);
  setButtonsDisabled(job.state === "running");
  updateProgressUI(job);
}

function switchSection(sectionId) {
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.section === sectionId);
  });
  document.querySelectorAll(".view-section").forEach((section) => {
    const active = section.id === `section-${sectionId}`;
    section.classList.toggle("active", active);
    if (active) {
      document.getElementById("page-title").textContent = section.dataset.title || sectionId;
      document.getElementById("page-subtitle").textContent = section.dataset.subtitle || "";
    }
  });
  document.getElementById("sidebar")?.classList.remove("open");
}

function bindNavigation() {
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
}

async function loadSummary() {
  const summary = await fetchJSON("/api/summary");
  renderStats(summary);
  renderSources(summary.sources);
  updateJobUI(summary.job || { state: "idle" });
  return summary.job;
}

async function loadActivities() {
  const params = new URLSearchParams({
    page: String(state.page),
    page_size: String(state.pageSize),
    draw: state.filters.draw || "active",
  });
  if (state.filters.q) params.set("q", state.filters.q);
  if (state.filters.type) params.set("type", state.filters.type);
  if (state.filters.status) params.set("status", state.filters.status);
  renderActivities(await fetchJSON(`/api/activities?${params.toString()}`));
}

async function startJob(action, params = {}) {
  if (!requireSetup(action)) return;
  const actionNames = { login: "扫码登录", refresh_all: "一键更新", participate: "参与活动" };
  showToast(`正在启动${actionNames[action] || action}`, "running", "任务日志已展开，可查看实时进度");
  toggleLogDock(true);
  try {
    await fetchJSON("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, params }),
    });
  } catch (error) {
    const message = sanitizeUserText(error.message || error);
    if (message.includes("请先扫码登录")) {
      showToast("请先扫码登录", "info", "完成登录与 LLM 配置后才能使用项目功能");
    } else if (message.includes("配置 LLM")) {
      showToast("请先配置 LLM", "info", "在概览页填写并保存 LLM 配置");
    } else {
      showToast(message, "error");
    }
    throw error;
  }
  if (action === "login") {
    state.qrcodeDismissed = false;
    state.lastQrcodeRefresh = 0;
    showQrcodeModal();
  }
  updateJobUI(await fetchJSON("/api/jobs/current"));
  startPolling();
}

function bindActionButtons() {
  document.querySelectorAll("[data-action]").forEach((button) => {
    if (button.dataset.bound === "true") return;
    button.dataset.bound = "true";
    button.addEventListener("click", async () => {
      const action = button.dataset.action;
      const params = {};
      if (button.dataset.dynamicId) params.dynamic_id = button.dataset.dynamicId;
      const originalText = button.textContent;
      if (action === "participate") {
        button.textContent = "参与中…";
        button.classList.add("is-loading");
      }
      try {
        await startJob(action, params);
      } catch (error) {
        showToast(String(error.message || error), "error");
        button.textContent = originalText;
        button.classList.remove("is-loading");
      }
    });
  });
}

function startPolling() {
  if (state.polling) return;
  state.polling = window.setInterval(async () => {
    const job = await fetchJSON("/api/jobs/current");
    updateJobUI(job);
    if (job.state === "running") {
      if (job.action === "login" && !state.qrcodeDismissed) {
        showQrcodeModal();
        if (qrcodeStatus) qrcodeStatus.textContent = sanitizeUserText(job.message) || "等待扫码确认…";
        const refreshedAt = Number(job.result?.qrcode_refreshed_at) || 0;
        if (refreshedAt && refreshedAt !== state.lastQrcodeRefresh) {
          state.lastQrcodeRefresh = refreshedAt;
          if (qrcodeImg) qrcodeImg.src = `/api/login/qrcode?t=${refreshedAt}`;
        }
      }
      return;
    }
    if (job.state === "idle" && job.action === "login") {
      window.clearInterval(state.polling);
      state.polling = null;
      setButtonsDisabled(false);
      hideQrcodeModal(false);
      updateJobUI(job);
      return;
    }
    const finishedDynamicId = job.action === "participate" ? job.result?.dynamic_id : null;
    if (job.state === "success") {
      showToast(sanitizeUserText(job.message) || "任务完成", "success", formatToastDetail(job));
    } else if (job.state === "error") {
      showToast(sanitizeUserText(job.message) || "任务失败", "error", formatToastDetail(job));
    }
    window.clearInterval(state.polling);
    state.polling = null;
    await loadSummary();
    await loadAccount();
    await loadSettings();
    await loadActivities();
    document.querySelectorAll("[data-action='participate'].is-loading").forEach((btn) => {
      btn.textContent = "参与";
      btn.classList.remove("is-loading");
    });
    if (finishedDynamicId) {
      document.querySelectorAll("tr").forEach((row) => {
        if (row.textContent?.includes(finishedDynamicId)) {
          row.classList.add("row-flash");
          window.setTimeout(() => row.classList.remove("row-flash"), 1800);
        }
      });
    }
    if (job.action === "login") hideQrcodeModal(false);
  }, 900);
}

function bindFilterPills() {
  document.querySelectorAll("[data-filter-type]").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll("[data-filter-type]").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      state.filters.type = button.dataset.filterType || "";
      state.page = 1;
      loadActivities();
    });
  });
  document.querySelectorAll("[data-filter-status]").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll("[data-filter-status]").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      state.filters.status = button.dataset.filterStatus || "";
      state.page = 1;
      loadActivities();
    });
  });
  const filterQ = document.getElementById("filter-q");
  let searchTimer = null;
  filterQ.addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => {
      state.page = 1;
      state.filters.q = filterQ.value.trim();
      loadActivities();
    }, 320);
  });
}

document.getElementById("save-llm-settings")?.addEventListener("click", async () => {
  try {
    await saveLlmSettings();
  } catch (error) {
    showToast(String(error.message || error), "error");
  }
});

document.getElementById("reset-llm-settings")?.addEventListener("click", async () => {
  try {
    await resetLlmSettings();
  } catch (error) {
    showToast(String(error.message || error), "error");
  }
});

document.getElementById("save-participate-text")?.addEventListener("click", async () => {
  try {
    await saveParticipateText();
  } catch (error) {
    showToast(String(error.message || error), "error");
  }
});

document.getElementById("reset-participate-text")?.addEventListener("click", async () => {
  try {
    await resetParticipateText();
  } catch (error) {
    showToast(String(error.message || error), "error");
  }
});

sidebarRefreshBtn?.addEventListener("click", async () => {
  const originalText = sidebarRefreshBtn.textContent;
  sidebarRefreshBtn.disabled = true;
  sidebarRefreshBtn.textContent = "刷新中…";
  try {
    await loadAccount();
    showToast("账号信息已更新", "success");
  } catch (error) {
    showToast(String(error.message || error), "error");
  } finally {
    sidebarRefreshBtn.disabled = false;
    sidebarRefreshBtn.textContent = originalText;
  }
});

sidebarLogoutBtn?.addEventListener("click", async () => {
  sidebarLogoutBtn.disabled = true;
  try {
    await logoutAccount();
  } catch (error) {
    showToast(String(error.message || error), "error");
  } finally {
    sidebarLogoutBtn.disabled = false;
  }
});

async function init() {
  bindNavigation();
  bindFilterPills();
  bindActionButtons();
  await loadAccount();
  await loadSettings();
  const job = await loadSummary();
  await loadActivities();
  if (job?.state === "running") startPolling();
}

init().catch((error) => {
  showToast(String(error.message || error), "error");
});
