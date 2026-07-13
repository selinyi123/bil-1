const state = {
  page: 1,
  pageSize: 30,
  filters: { q: "", type: "", status: "", draw: "", drawWindow: "", sort: "", order: "" },
  polling: null,
  logDockOpen: false,
  qrcodeDismissed: false,
  lastQrcodeRefresh: 0,
  account: null,
  settings: null,
  atAlertShownKey: "",
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
const filterDrawWindowHint = document.getElementById("filter-draw-window-hint");
const pagination = document.getElementById("pagination");
const qrcodeModal = document.getElementById("qrcode-modal");
const qrcodeImg = document.getElementById("qrcode-img");
const qrcodeTitle = document.getElementById("qrcode-title");
const qrcodeFrame = document.getElementById("qrcode-frame");
const qrcodeOverlay = document.getElementById("qrcode-overlay");
const qrcodeOverlayIcon = document.getElementById("qrcode-overlay-icon");
const qrcodeOverlayText = document.getElementById("qrcode-overlay-text");
const qrcodeStatus = document.getElementById("qrcode-status");
const progressBanner = document.getElementById("progress-banner");
const progressLabel = document.getElementById("progress-label");
const progressDetail = document.getElementById("progress-detail");
const progressFill = document.getElementById("progress-fill");
const progressFillGlow = document.getElementById("progress-fill-glow");
const progressPercent = document.getElementById("progress-percent");
const progressRing = document.getElementById("progress-ring");
const progressChip = document.getElementById("progress-chip");
const progressSteps = document.getElementById("progress-steps");
const toastStack = document.getElementById("toast-stack");
const logDock = document.getElementById("log-dock");
const logDockPanel = document.getElementById("log-dock-panel");
const logDockToggle = document.getElementById("log-dock-toggle");
const logDockBadge = document.getElementById("log-dock-badge");

const PARTICIPATE_STEP_LABELS = ["点赞", "关注", "收藏", "转发", "评论"];
const REFRESH_ALL_PIPELINE = ["数据源", "合并", "分类", "详情", "状态"];
const ACTION_LABELS = {
  like: "点赞",
  follow: "关注",
  favorite: "收藏",
  repost: "转发",
  comment: "评论",
  reserve: "预约",
};
const LOGIN_REQUIRED_ACTIONS = new Set(["refresh_all", "refresh_status", "participate"]);
const LLM_REQUIRED_ACTIONS = new Set(["refresh_all", "participate"]);

function isLoggedIn() {
  return Boolean(state.account?.logged_in && !state.account?.expired);
}

function isLlmConfigured() {
  return Boolean(state.settings?.llm?.configured);
}

function isLlmTested() {
  return Boolean(state.settings?.llm?.test_passed);
}

function isSetupComplete() {
  return isLoggedIn() && isLlmConfigured() && isLlmTested();
}

function requireSetup(action) {
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

function renderSetupChecklist() {
  const loggedIn = isLoggedIn();
  const llmOk = isLlmConfigured();
  const llmTested = isLlmTested();
  return `
    <div class="setup-checklist">
      <span class="setup-pill ${loggedIn ? "ok" : "warn"}">账号${loggedIn ? "已登录" : "未登录"}</span>
      <span class="setup-pill ${llmOk ? "ok" : "warn"}">LLM${llmOk ? "已配置" : "未配置"}</span>
      <span class="setup-pill ${llmTested ? "ok" : "warn"}">连接${llmTested ? "已通过" : "未测试"}</span>
    </div>`;
}

function renderAccountStatusLabel(account) {
  if (isSetupComplete()) return "已就绪";
  if (account.expired) return "需重新扫码登录";
  if (!isLlmConfigured()) return "请完成 LLM 配置";
  if (!isLlmTested()) return "请完成 LLM 连接测试";
  return "请完成登录与配置";
}

function sanitizeUserText(text) {
  const raw = String(text || "").trim();
  if (!raw) return "";
  const internalLinePattern =
    /traceback|nameerror|attributeerror|typeerror|keyerror|modulenotfounderror|oserror|systemexit|uvicorn|asyncio|^file\s/i;
  const internalFragmentPattern = /line \d+|\.py\b|errno|winerror/i;
  const lines = raw
    .split("\n")
    .map((line) => {
      const trimmed = line.trim();
      if (!trimmed) return "";
      if (internalLinePattern.test(trimmed)) return "";
      if (internalFragmentPattern.test(trimmed) && !/^===\s/.test(trimmed)) return "";
      return trimmed
        .replace(/[A-Za-z]:\\[^\s"']+/g, "[本地文件]")
        .replace(/→\s*\S+/g, "→ 已保存");
    })
    .filter(Boolean);
  return lines.join("\n");
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
  if (status === "已结束") return "badge ended";
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

function ensureQrcodeModalVisible() {
  if (!qrcodeModal || state.qrcodeDismissed) return;
  qrcodeModal.hidden = false;
  document.body.classList.add("modal-open");
}

function loadQrcodeImage(refreshedAt) {
  if (!qrcodeImg || !refreshedAt) return;
  const url = `/api/login/qrcode?t=${refreshedAt}`;
  qrcodeImg.onerror = () => {
    window.setTimeout(() => {
      if (!qrcodeImg.src.includes(`t=${refreshedAt}`)) return;
      qrcodeImg.src = `${url}&retry=1`;
    }, 400);
  };
  qrcodeImg.src = url;
}

function openQrcodeModalFresh() {
  ensureQrcodeModalVisible();
  if (qrcodeImg) qrcodeImg.removeAttribute("src");
  renderQrcodeLoginState({ result: { login_phase: "waiting" }, message: "正在生成登录二维码…" });
}

function resolveLoginPhase(job) {
  const fromResult = job?.result?.login_phase;
  if (fromResult) return String(fromResult);
  const msg = String(job?.message || "");
  if (msg.includes("登录成功")) return "success";
  if (msg.includes("正在完成登录") || msg.includes("正在写入") || msg.includes("已确认")) return "confirming";
  if (msg.includes("请在手机上") || msg.includes("扫码成功")) return "scanned";
  if (msg.includes("二维码已过期") || msg.includes("二维码已刷新")) return "refreshing";
  if (msg.includes("扫码登录超时") || msg.includes("登录失败") || msg.includes("重新扫码")) return "error";
  return "waiting";
}

function renderQrcodeLoginState(job) {
  const phase = resolveLoginPhase(job);
  const message = sanitizeUserText(job?.message) || "等待扫码…";
  const titles = {
    waiting: "使用哔哩哔哩 App 扫码",
    scanned: "请在手机上确认登录",
    confirming: "正在登录…",
    refreshing: "二维码已刷新",
    success: "登录成功",
    error: "登录失败",
  };
  if (qrcodeTitle) qrcodeTitle.textContent = titles[phase] || titles.waiting;
  if (qrcodeModal) qrcodeModal.dataset.phase = phase;
  if (qrcodeFrame) qrcodeFrame.dataset.phase = phase;
  if (qrcodeStatus) {
    qrcodeStatus.textContent = message;
    qrcodeStatus.classList.toggle("is-success", phase === "success");
    qrcodeStatus.classList.toggle("is-pending", phase === "scanned" || phase === "confirming");
    qrcodeStatus.classList.toggle("is-error", phase === "error");
  }
  const showOverlay = phase === "scanned" || phase === "confirming" || phase === "success" || phase === "error";
  if (qrcodeOverlay) qrcodeOverlay.hidden = !showOverlay;
  if (qrcodeOverlayText) {
    const overlayText = {
      scanned: "等待手机确认",
      confirming: "正在写入登录信息",
      success: "即将进入控制台",
      error: "请关闭后重新扫码",
    };
    qrcodeOverlayText.textContent = overlayText[phase] || "";
  }
  if (qrcodeOverlayIcon) {
    if (phase === "confirming") {
      qrcodeOverlayIcon.textContent = "";
    } else if (phase === "error") {
      qrcodeOverlayIcon.textContent = "!";
    } else {
      qrcodeOverlayIcon.textContent = "✓";
    }
  }
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

function renderPipelineSteps(labels, activeIndex) {
  if (!progressSteps) return;
  progressSteps.hidden = false;
  progressSteps.innerHTML = labels
    .map((label, index) => {
      let stepState = "pending";
      if (index < activeIndex) stepState = "done";
      else if (index === activeIndex) stepState = "active";
      const connector = index < labels.length - 1 ? `<span class="pipeline-connector ${index < activeIndex ? "done" : ""}"></span>` : "";
      return `
        <div class="pipeline-node ${stepState}">
          <span class="pipeline-dot" aria-hidden="true">${stepState === "done" ? "✓" : index + 1}</span>
          <span class="pipeline-label">${label}</span>
        </div>${connector}`;
    })
    .join("");
}

function renderParticipateSteps(job) {
  if (!progressSteps) return;
  if (job.state !== "running" || job.action !== "participate") {
    if (job.state === "running" && job.action === "refresh_all") {
      renderRefreshAllPipeline(job);
      return;
    }
    progressSteps.hidden = true;
    progressSteps.innerHTML = "";
    return;
  }
  const total = Number(job.progress_total) || PARTICIPATE_STEP_LABELS.length;
  const current = Number(job.progress_step) || 0;
  const labels = total === 1 ? ["预约"] : PARTICIPATE_STEP_LABELS.slice(0, total);
  const activeIndex = Math.max(0, Math.min(labels.length - 1, current > 0 ? current - 1 : 0));
  renderPipelineSteps(labels, activeIndex);
}

function refreshAllDataSourceCount(job) {
  const total = Number(job.progress_total) || 10;
  return Math.max(1, total - 4);
}

function renderRefreshAllPipeline(job) {
  if (!progressSteps) return;
  const step = Number(job.progress_step) || 0;
  const dsCount = refreshAllDataSourceCount(job);
  let phase = 0;
  if (step <= dsCount) phase = 0;
  else if (step === dsCount + 1) phase = 1;
  else if (step === dsCount + 2) phase = 2;
  else if (step === dsCount + 3) phase = 3;
  else phase = 4;
  renderPipelineSteps(REFRESH_ALL_PIPELINE, phase);
}

function calcJobProgressPercent(job) {
  const total = Number(job.progress_total) || 0;
  const step = Number(job.progress_step) || 0;
  if (total <= 0) return 8;
  if (job.action === "refresh_all") {
    const dsCount = refreshAllDataSourceCount(job);
    if (step <= 0) return 6;
    if (step <= dsCount) return Math.round(10 + (step / dsCount) * 44);
    if (step === dsCount + 1) return 62;
    if (step === dsCount + 2) return 72;
    if (step === dsCount + 3) {
      const detail = String(job.progress_message || "");
      if (detail.includes("本地活动缓存") || detail.includes("跳过详情")) return 84;
      const match = detail.match(/\((\d+)\s*\/\s*(\d+)\)/);
      if (match) {
        const ratio = Number(match[1]) / Math.max(1, Number(match[2]));
        return Math.min(90, Math.round(74 + ratio * 14));
      }
      return 76;
    }
    if (step >= dsCount + 4) return Math.min(100, 96);
  }
  if (job.action === "participate") {
    const subTotal = Number(job.progress_total) || 5;
    const subStep = Number(job.progress_step) || 0;
    if (subTotal <= 0) return 12;
    const ratio = Math.min(1, subStep / subTotal);
    return Math.max(8, Math.min(98, Math.round(8 + ratio * 90)));
  }
  return Math.max(8, Math.min(100, Math.round((step / total) * 100)));
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
    { label: "已结束", value: counts["已结束"] || 0 },
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

function formatAccountStat(value, loggedIn) {
  if (value === null || value === undefined) {
    return loggedIn ? 0 : "—";
  }
  return value;
}

function renderAtAlertBanner(account) {
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

function maybeShowAtUnreadAlert(account) {
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

async function acknowledgeAtUnread(current) {
  await fetchJSON("/api/account/ack-at-unread", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ current: Number(current) || 0 }),
    timeoutMs: 20000,
  });
  state.atAlertShownKey = "";
  return loadAccount();
}

function bindAtAlertActions(account) {
  document.getElementById("account-at-ack-btn")?.addEventListener("click", async () => {
    try {
      await acknowledgeAtUnread(account.unread_at ?? 0);
      showToast("已记录当前 @ 未读数", "success");
    } catch (error) {
      showToast(String(error.message || error), "error");
    }
  });
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
          <span class="account-status warn">需完成登录、LLM 配置与连接测试</span>
        </div>
      </div>`;
    if (accountHero) accountHero.innerHTML = emptyHtml;
    if (sidebarAccountCard) {
      sidebarAccountCard.innerHTML = `
        <div class="sidebar-account-mini" title="${escapeHtml(account.message || "请扫码登录")}">
          <div class="account-avatar account-avatar-fallback"></div>
          <div class="sidebar-account-text">
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
  const atNotifyUrl = account.at_notify_url || "https://message.bilibili.com/#/notify/at";
  const atUnread = Number(formatAccountStat(account.unread_at, loggedIn)) || 0;
  const heroHtml = `
    ${avatar}
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
          <span class="account-stat-value">${formatAccountStat(account.unread_messages, loggedIn)}</span>
          <span class="account-stat-label">私信未读</span>
        </div>
        <div class="account-stat account-stat-at${atUnread > 0 ? " has-unread" : ""}">
          <span class="account-stat-value">${formatAccountStat(account.unread_at, loggedIn)}</span>
          <span class="account-stat-label">
            <span>@我的</span>
            <a class="account-stat-inline-link" href="${escapeHtml(atNotifyUrl)}" target="_blank" rel="noopener noreferrer" title="在 B 站查看 @ 我的通知">查看</a>
          </span>
        </div>
      </div>
      <div class="account-hero-footer">
        ${renderSetupChecklist()}
        <span class="account-status ${isSetupComplete() ? "ok" : "warn"}">${escapeHtml(renderAccountStatusLabel(account))}</span>
      </div>
    </div>`;
  if (accountHero) accountHero.innerHTML = heroHtml;
  bindAtAlertActions(account);

  const sidebarAvatar = account.face
    ? `<img class="account-avatar" src="${escapeHtml(account.face)}" alt="头像" referrerpolicy="no-referrer" crossorigin="anonymous" />`
    : `<div class="account-avatar account-avatar-fallback"></div>`;
  if (sidebarAccountCard) {
    sidebarAccountCard.innerHTML = `
      <div class="sidebar-account-mini" title="${escapeHtml(account.uname || "B站用户")}">
        ${sidebarAvatar}
        <div class="sidebar-account-text">
          <p class="sidebar-account-name">${escapeHtml(account.uname || "B站用户")}</p>
          <p class="sidebar-account-sub">UID ${escapeHtml(account.mid || "—")}</p>
        </div>
      </div>`;
  }
}

async function loadAccount() {
  const account = await fetchJSON("/api/account", { timeoutMs: 20000 });
  renderAccountViews(account);
  maybeShowAtUnreadAlert(account);
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
      unread_at: null,
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
  return settings;
}

async function syncProjectState() {
  const account = await loadAccount();
  await loadSettings();
  if (state.account) renderAccountViews(state.account);
  return account;
}

function getLlmFormValues() {
  return {
    api_key: document.getElementById("llm-api-key-input")?.value || "",
    base_url: document.getElementById("llm-base-url-input")?.value || "",
    model_name: document.getElementById("llm-model-name-input")?.value || "",
  };
}

function renderLlmSettingsForm(settings) {
  const llm = settings?.llm || {};
  const baseInput = document.getElementById("llm-base-url-input");
  const modelInput = document.getElementById("llm-model-name-input");
  const keyInput = document.getElementById("llm-api-key-input");
  const keyHint = document.getElementById("llm-api-key-hint");
  const baseHint = document.getElementById("llm-base-url-hint");
  const status = document.getElementById("llm-settings-status");
  if (baseInput) baseInput.value = llm.base_url || "";
  if (modelInput) modelInput.value = llm.model_name || "";
  if (keyInput) {
    keyInput.value = "";
    keyInput.placeholder = llm.configured ? "已配置，留空则不修改" : "请输入 API Key";
  }
  if (keyHint) {
    keyHint.textContent = llm.configured
      ? `当前 Key：${llm.api_key_hint || "****"}（输入新 Key 可覆盖）`
      : "尚未保存 API Key";
  }
  if (baseHint) {
    baseHint.textContent = `当前接口：${llm.base_url || "（空）"}`;
  }
  if (status) {
    if (!isLoggedIn()) {
      status.textContent = llm.configured
        ? "已从本地配置文件读取，登录后可修改并保存"
        : "需先登录，再保存 LLM 配置";
    } else if (llm.configured && !llm.test_passed) {
      status.textContent = "配置已保存，请先测试连接通过后再使用项目功能";
    } else if (llm.configured) status.textContent = "LLM 已配置且测试通过";
    else status.textContent = "请填写 API Key 与模型名称并保存，完成后才能使用项目功能";
  }
}

async function refreshLlmSettings() {
  const button = document.getElementById("refresh-llm-settings");
  const originalText = button?.textContent || "刷新配置";
  if (button) {
    button.disabled = true;
    button.textContent = "刷新中…";
  }
  try {
    const result = await fetchJSON("/api/settings/llm");
    state.settings = { ...(state.settings || {}), llm: result.llm, setup_complete: result.setup_complete };
    renderLlmSettingsForm(state.settings);
    if (state.account) renderAccountViews(state.account);
    const detail = result.llm?.configured
      ? `${result.llm.model_name || "已配置"} · ${result.llm.api_key_hint || ""}`
      : "本地配置文件为空或未完整填写";
    showToast("配置已刷新", "success", detail);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = originalText;
    }
  }
}

async function saveLlmSettings() {
  if (!isLoggedIn()) {
    showToast("请先扫码登录", "info", "登录后才能配置 LLM");
    return;
  }
  const result = await fetchJSON("/api/settings/llm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(getLlmFormValues()),
  });
  state.settings = { ...(state.settings || {}), llm: result.llm, setup_complete: result.setup_complete };
  renderLlmSettingsForm(state.settings);
  if (state.account) renderAccountViews(state.account);
  showToast("LLM 配置已保存", "success", `${result.llm.model_name || "已配置"} · ${result.llm.api_key_hint || ""}`);
}

async function testLlmSettings() {
  if (!isLoggedIn()) {
    showToast("请先扫码登录", "info", "登录后才能测试 LLM");
    return;
  }
  const button = document.getElementById("test-llm-settings");
  const originalText = button?.textContent || "测试连接";
  if (button) {
    button.disabled = true;
    button.textContent = "测试中…";
  }
  try {
    const result = await fetchJSON("/api/settings/llm/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(getLlmFormValues()),
      timeoutMs: 60000,
    });
    state.settings = {
      ...(state.settings || {}),
      llm: result.llm,
      setup_complete: result.setup_complete,
    };
    renderLlmSettingsForm(state.settings);
    if (state.account) renderAccountViews(state.account);
    showToast("LLM 连接正常", "success", result.message || "");
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = originalText;
    }
  }
}

async function saveParticipateText() {
  if (!isLoggedIn()) {
    showToast("请先扫码登录", "info", "登录后才能修改参与文案");
    return;
  }
  const input = document.getElementById("participate-text-input");
  const button = document.getElementById("save-participate-text");
  const value = input?.value?.trim() || "";
  const originalText = button?.textContent || "保存文案";
  if (button) {
    button.disabled = true;
    button.textContent = "保存中…";
  }
  try {
    const result = await fetchJSON("/api/settings/participate-text", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ participate_text: value }),
    });
    if (input) input.value = result.participate_text;
    if (state.settings) state.settings.participate_text = result.participate_text;
    showToast("参与文案已保存", "success", result.participate_text);
  } catch (error) {
    showToast(String(error.message || error), "error");
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = originalText;
    }
  }
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
    activitiesBody.innerHTML = `<tr class="empty-row"><td colspan="7">没有匹配的活动</td></tr>`;
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
        const checkAtHint = item.check_at_recommended
          ? `<div class="activity-check-at-hint">已开奖，建议查看 @我的 通知</div>`
          : "";
        return `
          <tr>
            <td class="activity-cell">
              <div class="activity-title">${escapeHtml(item.activity_title || item.prize || "未知活动")}</div>
              ${checkAtHint}
              ${lastNote}
            </td>
            <td class="link-cell">${linkCell}</td>
            <td class="chip-cell"><span class="type-chip">${escapeHtml(item.lottery_type)}</span></td>
            <td class="heat-cell"><span class="heat-pill${item.heat_missing ? " heat-pill-missing" : ""}">${formatHeat(item)}</span></td>
            <td class="chip-cell"><span class="${badgeClass(item.activity_status)}">${escapeHtml(item.activity_status)}</span></td>
            <td class="time-cell"><span class="time-pill">${escapeHtml(formatLotteryTime(item.lottery_time))}</span></td>
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
  document.body.classList.toggle("job-running", running);
  progressBanner.hidden = !running;
  if (!running) {
    progressFill.style.width = "0%";
    if (progressFillGlow) progressFillGlow.style.width = "0%";
    const shine = document.getElementById("progress-fill-shine");
    if (shine) shine.style.left = "0%";
    if (progressPercent) progressPercent.textContent = "0";
    if (progressRing) progressRing.style.strokeDashoffset = "97.4";
    renderParticipateSteps(job);
    return;
  }
  const percent = calcJobProgressPercent(job);
  const prev = Number(progressBanner.dataset.percent || "0");
  progressBanner.dataset.percent = String(percent);
  if (percent > prev) progressBanner.classList.add("progress-tick");
  else progressBanner.classList.remove("progress-tick");
  window.setTimeout(() => progressBanner.classList.remove("progress-tick"), 420);
  progressFill.style.width = `${percent}%`;
  if (progressFillGlow) progressFillGlow.style.width = `${percent}%`;
  const shine = document.getElementById("progress-fill-shine");
  if (shine) shine.style.left = `${Math.max(0, percent - 6)}%`;
  if (progressPercent) progressPercent.textContent = String(percent);
  if (progressRing) {
    const circumference = 97.4;
    progressRing.style.strokeDashoffset = String(circumference - (circumference * percent) / 100);
  }
  if (progressChip) {
    const chipMap = { participate: "参与任务", refresh_all: "同步任务", login: "登录任务" };
    progressChip.textContent = chipMap[job.action] || "任务进行中";
  }
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

function formatHeat(item) {
  if (item?.heat_missing) return "—";
  const value = Number(item?.repost_count) || 0;
  if (value >= 10000) return `${(value / 10000).toFixed(1)}万`;
  return String(value);
}

function formatLotteryTime(value) {
  const text = String(value || "").trim();
  if (!text || text === "—") return "—";
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/.test(text)) return text;
  return "—";
}

async function refreshActivityStatus() {
  if (!isLoggedIn()) {
    showToast("请先扫码登录", "info", "登录后才能刷新活动状态");
    return;
  }
  const button = document.getElementById("refresh-status-btn");
  const originalText = button?.textContent || "刷新任务状态";
  if (button) {
    button.disabled = true;
    button.textContent = "刷新中…";
  }
  try {
    const result = await fetchJSON("/api/activities/refresh-status", { method: "POST" });
    const drawnCount = Number(result.draw_reminder?.drawn_participated_count) || 0;
    if (drawnCount > 0) {
      showToast(
        result.message || "状态已刷新",
        "info",
        `${drawnCount} 个已参加活动已开奖，建议打开 B 站查看 @我的 通知。`
      );
    } else {
      showToast(result.message || "状态已刷新", "success");
    }
    await loadActivities();
    const summary = await fetchJSON("/api/summary");
    renderStats(summary);
  } catch (error) {
    showToast(sanitizeUserText(error.message || error), "error");
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = originalText;
    }
  }
}

function setFilterPillGroup(selector, activeButton) {
  document.querySelectorAll(selector).forEach((item) => {
    const active = item === activeButton;
    item.classList.toggle("active", active);
    item.setAttribute("aria-pressed", active ? "true" : "false");
  });
}

function setStatusFilter(value) {
  state.filters.status = value || "";
  const buttons = document.querySelectorAll("[data-filter-status]");
  let matched = false;
  buttons.forEach((button) => {
    const isActive = (button.getAttribute("data-filter-status") || "") === state.filters.status;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-pressed", isActive ? "true" : "false");
    if (isActive) matched = true;
  });
  if (!matched && buttons[0]) {
    buttons[0].classList.add("active");
    buttons[0].setAttribute("aria-pressed", "true");
  }
}

function setDrawWindowFilter(value) {
  state.filters.drawWindow = value || "";
  document.querySelectorAll("[data-filter-draw-window]").forEach((button) => {
    const isActive = (button.getAttribute("data-filter-draw-window") || "") === state.filters.drawWindow;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-pressed", isActive ? "true" : "false");
  });
  if (filterDrawWindowHint) {
    filterDrawWindowHint.hidden = !state.filters.drawWindow;
  }
}

function updateDrawWindowHint() {
  if (!filterDrawWindowHint || !state.filters.drawWindow) return;
  const label = state.filters.drawWindow === "drawn" ? "已开奖" : "即将开奖";
  filterDrawWindowHint.textContent = `仅筛选你已参加的活动 · ${label}（近 3 天）`;
}

async function loadActivities() {
  const params = new URLSearchParams({
    page: String(state.page),
    page_size: String(state.pageSize),
  });
  if (state.filters.draw) params.set("draw", state.filters.draw);
  if (state.filters.q) params.set("q", state.filters.q);
  if (state.filters.type) params.set("type", state.filters.type);
  if (state.filters.status) params.set("status", state.filters.status);
  if (state.filters.drawWindow) params.set("draw_window", state.filters.drawWindow);
  if (state.filters.sort) params.set("sort", state.filters.sort);
  if (state.filters.order) params.set("order", state.filters.order);
  try {
    renderActivities(await fetchJSON(`/api/activities?${params.toString()}`));
  } catch (error) {
    showToast(String(error.message || error), "error");
  }
}

async function startJob(action, params = {}) {
  if (!requireSetup(action)) return;
  if (action === "login") {
    try {
      const current = await fetchJSON("/api/jobs/current");
      if (current.state === "running" && current.action === "login") {
        state.qrcodeDismissed = false;
        ensureQrcodeModalVisible();
        const refreshedAt = Number(current.result?.qrcode_refreshed_at) || 0;
        if (refreshedAt && refreshedAt !== state.lastQrcodeRefresh) {
          state.lastQrcodeRefresh = refreshedAt;
          loadQrcodeImage(refreshedAt);
        }
        renderQrcodeLoginState(current);
        startPolling();
        return;
      }
    } catch {
      /* 继续发起新任务 */
    }
  }
  const actionNames = { login: "扫码登录", refresh_all: "一键更新", refresh_status: "刷新任务状态", participate: "参与活动" };
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
    } else if (message.includes("连接测试") || message.includes("测试")) {
      showToast("请先测试 LLM 连接", "info", "保存配置后点击「测试连接」，通过后才能使用项目功能");
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
    openQrcodeModalFresh();
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
  const poll = async () => {
    try {
      const job = await fetchJSON("/api/jobs/current");
      updateJobUI(job);
      if (job.state === "running") {
        if (job.action === "login" && !state.qrcodeDismissed) {
          ensureQrcodeModalVisible();
          renderQrcodeLoginState(job);
          const refreshedAt = Number(job.result?.qrcode_refreshed_at) || 0;
          if (refreshedAt && refreshedAt !== state.lastQrcodeRefresh) {
            state.lastQrcodeRefresh = refreshedAt;
            loadQrcodeImage(refreshedAt);
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
      if (job.action === "login" && job.state === "success" && !state.qrcodeDismissed) {
        renderQrcodeLoginState({ ...job, result: { ...(job.result || {}), login_phase: "success" }, message: "登录成功，账号已就绪" });
        await new Promise((resolve) => window.setTimeout(resolve, 450));
      }
      if (job.state === "success") {
        const detail = formatToastDetail(job);
        showToast(sanitizeUserText(job.message) || "任务完成", "success", detail);
      } else if (job.state === "error") {
        if (job.action === "login" && !state.qrcodeDismissed) {
          renderQrcodeLoginState({
            ...job,
            result: { ...(job.result || {}), login_phase: "error" },
            message: sanitizeUserText(job.message) || "登录失败，请重试",
          });
        }
        showToast(sanitizeUserText(job.message) || "任务失败", "error", formatToastDetail(job));
      }
      window.clearInterval(state.polling);
      state.polling = null;
      try {
        await loadSummary();
        await syncProjectState();
        await loadActivities();
      } catch (error) {
        showToast(String(error.message || error), "error");
      }
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
      if (job.action === "login" && job.state === "success") hideQrcodeModal(false);
    } catch (error) {
      console.error(error);
    }
  };
  poll();
  const intervalMs = 200;
  state.polling = window.setInterval(poll, intervalMs);
}

function bindFilterPills() {
  document.querySelectorAll("[data-filter-type]").forEach((button) => {
    button.addEventListener("click", () => {
      setFilterPillGroup("[data-filter-type]", button);
      state.filters.type = button.getAttribute("data-filter-type") || "";
      state.page = 1;
      loadActivities();
    });
  });
  document.querySelectorAll("[data-filter-status]").forEach((button) => {
    button.addEventListener("click", () => {
      if (state.filters.drawWindow) {
        setDrawWindowFilter("");
      }
      setFilterPillGroup("[data-filter-status]", button);
      state.filters.status = button.getAttribute("data-filter-status") || "";
      state.page = 1;
      loadActivities();
    });
  });
  document.querySelectorAll("[data-filter-sort]").forEach((button) => {
    button.addEventListener("click", () => {
      setFilterPillGroup("[data-filter-sort]", button);
      state.filters.sort = button.getAttribute("data-filter-sort") || "";
      state.filters.order = button.getAttribute("data-filter-order") || "";
      state.page = 1;
      loadActivities();
    });
  });
  document.querySelectorAll("[data-filter-draw-window]").forEach((button) => {
    button.addEventListener("click", () => {
      const value = button.getAttribute("data-filter-draw-window") || "";
      const isActive = button.classList.contains("active");
      if (isActive) {
        setDrawWindowFilter("");
      } else {
        setStatusFilter("");
        setDrawWindowFilter(value);
        updateDrawWindowHint();
      }
      state.page = 1;
      loadActivities();
    });
  });
  const filterQ = document.getElementById("filter-q");
  if (!filterQ) return;
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

document.getElementById("refresh-llm-settings")?.addEventListener("click", async () => {
  try {
    await refreshLlmSettings();
  } catch (error) {
    showToast(String(error.message || error), "error");
  }
});

document.getElementById("test-llm-settings")?.addEventListener("click", async () => {
  try {
    await testLlmSettings();
  } catch (error) {
    showToast(String(error.message || error), "error");
  }
});

document.getElementById("save-llm-settings")?.addEventListener("click", async () => {
  try {
    await saveLlmSettings();
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
    const account = await syncProjectState();
    if (!account?.at_alert?.increased) {
      showToast("状态已同步", "success");
    }
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
  initSystemPreferences();
  bindNavigation();
  bindFilterPills();
  bindActionButtons();
  await syncProjectState();
  const job = await loadSummary();
  await loadActivities();
  if (job?.state === "running") startPolling();
}

function initSystemPreferences() {
  applySidebarCollapsed(localStorage.getItem("binggo-sidebar-collapsed") === "1");
  applyTheme(localStorage.getItem("binggo-theme") === "dark" ? "dark" : "light");
  document.getElementById("sidebar-collapse")?.addEventListener("click", () => {
    const collapsed = !document.querySelector(".app-shell")?.classList.contains("sidebar-collapsed");
    applySidebarCollapsed(collapsed);
  });
  document.getElementById("theme-toggle")?.addEventListener("click", () => {
    const isDark = document.documentElement.dataset.theme === "dark";
    applyTheme(isDark ? "light" : "dark");
  });
  document.getElementById("refresh-status-btn")?.addEventListener("click", refreshActivityStatus);
}

function applySidebarCollapsed(collapsed) {
  document.querySelector(".app-shell")?.classList.toggle("sidebar-collapsed", collapsed);
  const btn = document.getElementById("sidebar-collapse");
  if (btn) {
    btn.classList.toggle("active", collapsed);
    btn.title = collapsed ? "展开侧边栏" : "收起侧边栏";
    const text = btn.querySelector(".system-btn-text");
    if (text) text.textContent = collapsed ? "展开侧栏" : "靠边收起";
  }
  localStorage.setItem("binggo-sidebar-collapsed", collapsed ? "1" : "0");
}

function applyTheme(theme) {
  const next = theme === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = next;
  const btn = document.getElementById("theme-toggle");
  if (btn) {
    btn.classList.toggle("active", next === "dark");
    const text = btn.querySelector(".system-btn-text");
    if (text) text.textContent = next === "dark" ? "日间模式" : "夜间模式";
    btn.querySelector(".icon-moon")?.toggleAttribute("hidden", next === "dark");
    btn.querySelector(".icon-sun")?.toggleAttribute("hidden", next !== "dark");
  }
  localStorage.setItem("binggo-theme", next);
}

window.addEventListener("pageshow", (event) => {
  if (!event.persisted) return;
  syncProjectState().catch((error) => {
    showToast(String(error.message || error), "error");
  });
});

init().catch((error) => {
  showToast(String(error.message || error), "error");
});
