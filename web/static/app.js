const state = {
  page: 1,
  pageSize: 20,
  filters: { q: "", type: "", status: "", draw: "", drawWindow: "", sort: "", order: "" },
  polling: null,
  logDockOpen: false,
  autoDockOpen: false,
  autoScheduler: null,
  autoPollTimer: null,
  autoCountdownTimer: null,
  autoServerSkewMs: 0,
  qrcodeDismissed: false,
  lastQrcodeRefresh: 0,
  account: null,
  settings: null,
  atAlertShownKey: "",
  tripleTargets: { count: 0, limit: 3, items: [] },
  tripleFilterKey: "",
  smoothJobPercent: 0,
  activeJobKey: "",
  jobResultTimer: null,
  watchUsers: null,
};

const jobMessage = document.getElementById("job-message");
const jobLog = document.getElementById("job-log");
const statsGrid = document.getElementById("stats-grid");
const sourceGrid = document.getElementById("source-grid");
const watchUserGrid = document.getElementById("watch-user-grid");
const watchUsersBadge = document.getElementById("watch-users-badge");
const watchMetricCount = document.getElementById("watch-metric-count");
const watchMetricLinks = document.getElementById("watch-metric-links");
const watchLastSynced = document.getElementById("watch-last-synced");
const watchNextWindow = document.getElementById("watch-next-window");
const watchWindowCap = document.getElementById("watch-window-cap");
const watchAddForm = document.getElementById("watch-add-form");
const watchAddMidInput = document.getElementById("watch-add-mid");
const watchAddMidError = document.getElementById("watch-add-mid-error");
const watchAddBtn = document.getElementById("watch-add-btn");
const accountHero = document.getElementById("account-hero");
const sidebarAccountCard = document.getElementById("sidebar-account-card");
const sidebarLoginBtn = document.getElementById("sidebar-login");
const sidebarLogoutBtn = document.getElementById("sidebar-logout");
const logoutConfirmModal = document.getElementById("logout-confirm-modal");
const logoutConfirmBackdrop = document.getElementById("logout-confirm-backdrop");
const logoutConfirmCancel = document.getElementById("logout-confirm-cancel");
const logoutConfirmYes = document.getElementById("logout-confirm-yes");
const sidebarRefreshBtn = document.getElementById("sidebar-refresh-account");
const activitiesBody = document.getElementById("activities-body");
const activitiesCards = document.getElementById("activities-cards");
const filterResultSummary = document.getElementById("filter-result-summary");
const participateTextFeedback = document.getElementById("participate-text-feedback");
const llmActionFeedback = document.getElementById("llm-action-feedback");
const filterDrawWindowHint = document.getElementById("filter-draw-window-hint");
const pagination = document.getElementById("pagination");
const qrcodeModal = document.getElementById("qrcode-modal");
const qrcodeImg = document.getElementById("qrcode-img");
const qrcodeTitle = document.getElementById("qrcode-title");
const qrcodeFrame = document.getElementById("qrcode-frame");
const qrcodeOverlay = document.getElementById("qrcode-overlay");
const qrcodeOverlayIcon = document.getElementById("qrcode-overlay-icon");
const qrcodeOverlayText = document.getElementById("qrcode-overlay-text");
const qrcodeClose = document.getElementById("qrcode-close");
const qrcodeStatus = document.getElementById("qrcode-status");
let qrcodeLastFocus = null;
const progressBanner = document.getElementById("progress-banner");
const progressLabel = document.getElementById("progress-label");
const progressDetail = document.getElementById("progress-detail");
const progressFill = document.getElementById("progress-fill");
const progressFillGlow = document.getElementById("progress-fill-glow");
const progressPercent = document.getElementById("progress-percent");
const progressPercentSuffix = document.querySelector(".progress-percent-suffix");
const progressRing = document.getElementById("progress-ring");
const progressTrack = document.getElementById("progress-track");
const progressChip = document.getElementById("progress-chip");
const progressSteps = document.getElementById("progress-steps");
const jobResultBanner = document.getElementById("job-result-banner");
const jobResultIcon = document.getElementById("job-result-icon");
const jobResultEyebrow = document.getElementById("job-result-eyebrow");
const jobResultTitle = document.getElementById("job-result-title");
const jobResultSummary = document.getElementById("job-result-summary");
const jobResultBody = document.getElementById("job-result-body");
const jobResultProgress = document.getElementById("job-result-progress");
const jobResultClose = document.getElementById("job-result-close");
const toastStack = document.getElementById("toast-stack");

const JOB_RESULT_AUTO_DISMISS_MS = 3000;
const JOB_RESULT_EXIT_MS = 340;
const JOB_RESULT_HOVER_DISMISS_MS = 2200;
const INLINE_FEEDBACK_MS = 5000;
const SYNC_TOAST_ACTIONS = new Set(["refresh_all", "refresh_source", "refresh_watch", "refresh_status"]);
const inlineFeedbackTimers = new Map();
const logDock = document.getElementById("log-dock");
const logDockPanel = document.getElementById("log-dock-panel");
const logDockToggle = document.getElementById("log-dock-toggle");
const logDockBadge = document.getElementById("log-dock-badge");
const autoDock = document.getElementById("auto-dock");
const autoDockPanel = document.getElementById("auto-dock-panel");
const autoDockToggle = document.getElementById("auto-dock-toggle");
const autoDockBadge = document.getElementById("auto-dock-badge");
const autoDockStatus = document.getElementById("auto-dock-status");
const autoDockCountdown = document.getElementById("auto-dock-countdown");
const autoDockJob = document.getElementById("auto-dock-job");
const autoDockPhase = document.getElementById("auto-dock-phase");
const autoDockHint = document.getElementById("auto-dock-hint");
const autoDockPipeline = document.getElementById("auto-dock-pipeline");
const autoDockNextTask = document.getElementById("auto-dock-next-task");
const autoDockFatal = document.getElementById("auto-dock-fatal");
const autoDockFatalText = document.getElementById("auto-dock-fatal-text");
const autoDockStartBtn = document.getElementById("auto-dock-start");
const autoDockStopBtn = document.getElementById("auto-dock-stop");
const autoDockRestartBtn = document.getElementById("auto-dock-restart");

const PARTICIPATE_STEP_LABELS = ["点赞", "关注", "收藏", "转发", "评论"];
const PARTICIPATE_ACTIVE_KEYWORDS = ["点赞", "关注", "收藏", "转发", "评论", "预约", "正在", "准备", "检查"];
const PARTICIPATE_DONE_KEYWORDS = ["完成", "成功", "已参与", "参与成功", "joined"];
const PARTICIPATE_FAIL_KEYWORDS = ["失败", "未完成", "错误", "failed", "已停止", "已取消"];
const PARTICIPATE_PENDING_KEYWORDS = ["排队", "等待"];
const REFRESH_ALL_PIPELINE = ["数据源", "分类", "详情", "落库"];
const REFRESH_WATCH_PIPELINE = ["扫描", "分类", "详情", "落库"];
const REFRESH_ALL_PIPELINE_SUBSTEPS = 3;
const REFRESH_WATCH_PIPELINE_SUBSTEPS = 3;
const REFRESH_ALL_DS_COUNT = 6;
const ACTION_LABELS = {
  like: "点赞",
  follow: "关注",
  favorite: "收藏",
  repost: "转发",
  comment: "评论",
  reserve: "预约",
};
const INTERACT_REQUIRED_ACTIONS = ["like", "follow", "favorite", "repost"];
const FORWARD_REQUIRED_ACTIONS = ["like", "follow", "favorite", "repost", "comment"];
const COMMENT_OPTIONAL_PATTERNS = [/关注UP主/i, /关注 up/i, /7\s*天/i, /code=12078/i];
const LOGIN_REQUIRED_ACTIONS = new Set([
  "refresh_all",
  "refresh_source",
  "refresh_watch",
  "refresh_status",
  "participate",
  "participate_triple",
]);
const LLM_REQUIRED_ACTIONS = new Set([
  "refresh_all",
  "refresh_source",
  "refresh_watch",
  "participate",
  "participate_triple",
]);

function isRefreshPipelineAction(action) {
  return action === "refresh_all" || action === "refresh_source";
}

let sectionSwitchTimer = null;

function prefersReducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function setButtonLoading(button, loading, options = {}) {
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

function clearActionButtonLoading() {
  document.querySelectorAll("[data-action].is-loading, .triple-participate-btn.is-loading").forEach((btn) => {
    setButtonLoading(btn, false);
  });
}

function pulseFilterSummary() {
  if (!filterResultSummary || prefersReducedMotion()) return;
  filterResultSummary.classList.remove("is-updated");
  void filterResultSummary.offsetWidth;
  filterResultSummary.classList.add("is-updated");
}

function highlightWatchUserChip(mid) {
  if (!mid) return;
  const chip = document.querySelector(`[data-watch-mid="${CSS.escape(String(mid))}"]`);
  if (!chip || prefersReducedMotion()) return;
  chip.classList.add("is-new");
  window.setTimeout(() => chip.classList.remove("is-new"), 700);
}

function formatUnixTimestamp(ts) {
  const value = Number(ts);
  if (!value) return "尚未同步";
  const date = new Date(value * 1000);
  if (Number.isNaN(date.getTime())) return "尚未同步";
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function formatWatchWindow(start, end) {
  const fmt = (ts) => {
    const value = Number(ts);
    if (!value) return "—";
    const date = new Date(value * 1000);
    if (Number.isNaN(date.getTime())) return "—";
    const pad = (n) => String(n).padStart(2, "0");
    return `${pad(date.getMonth() + 1)}/${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
  };
  const from = fmt(start);
  const to = fmt(end);
  if (from === "—" || to === "—") return "—";
  return `${from} — ${to}`;
}

function formatWindowDays(seconds) {
  const days = Math.max(1, Math.round(Number(seconds || 0) / 86400));
  return `${days} 天`;
}

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
    const response = await fetch(url, { cache: "no-store", ...fetchOptions, signal: controller.signal });
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

function dismissRunningToasts() {
  if (!toastStack) return;
  toastStack.querySelectorAll(".toast-running").forEach((toast) => toast.remove());
}

function setInlineFeedback(element, message, type = "info", { autoHide = true } = {}) {
  if (!element) return;
  const existing = inlineFeedbackTimers.get(element);
  if (existing) window.clearTimeout(existing);

  if (!message) {
    element.hidden = true;
    element.textContent = "";
    element.className = "inline-feedback";
    return;
  }

  element.hidden = false;
  element.textContent = message;
  element.className = `inline-feedback inline-feedback--${type}`;

  if (autoHide && type !== "info") {
    const timer = window.setTimeout(() => setInlineFeedback(element, "", "info"), INLINE_FEEDBACK_MS);
    inlineFeedbackTimers.set(element, timer);
  }
}

function toggleLlmApiKeyVisibility() {
  const input = document.getElementById("llm-api-key-input");
  const toggle = document.getElementById("llm-api-key-toggle");
  if (!input || !toggle) return;
  const showPlain = input.type === "password";
  input.type = showPlain ? "text" : "password";
  toggle.textContent = showPlain ? "隐藏" : "显示";
  toggle.setAttribute("aria-label", showPlain ? "隐藏 API Key" : "显示 API Key");
  toggle.setAttribute("aria-pressed", showPlain ? "true" : "false");
}

function bindLlmApiKeyToggle() {
  const toggle = document.getElementById("llm-api-key-toggle");
  if (!toggle || toggle.dataset.bound === "true") return;
  toggle.dataset.bound = "true";
  toggle.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    toggleLlmApiKeyVisibility();
  });
}

function getQrcodeFocusable() {
  const panel = qrcodeModal?.querySelector(".qrcode-panel");
  if (!panel) return [];
  return [...panel.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')]
    .filter((el) => !el.hidden && el.getAttribute("aria-hidden") !== "true");
}

function trapQrcodeFocus(event) {
  if (!qrcodeModal || qrcodeModal.hidden || event.key !== "Tab") return;
  const items = getQrcodeFocusable();
  if (!items.length) return;
  const first = items[0];
  const last = items[items.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

function ensureQrcodeModalVisible() {
  if (!qrcodeModal || state.qrcodeDismissed) return;
  qrcodeLastFocus = document.activeElement;
  qrcodeModal.hidden = false;
  document.body.classList.add("modal-open");
  window.requestAnimationFrame(() => qrcodeClose?.focus());
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
  if (qrcodeLastFocus && typeof qrcodeLastFocus.focus === "function") {
    qrcodeLastFocus.focus();
  }
  qrcodeLastFocus = null;
}

async function cancelLoginJob() {
  try {
    const job = await fetchJSON("/api/jobs/current");
    if (job.state === "running" && job.action === "login") {
      await fetchJSON("/api/jobs/cancel", { method: "POST" });
      stopJobPolling();
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
  logDockPanel.classList.toggle("is-open", open);
  logDockPanel.setAttribute("aria-hidden", String(!open));
  logDockToggle.hidden = open;
  logDockToggle.setAttribute("aria-expanded", String(open));
  logDock?.classList.toggle("open", open);
}

function toggleLogDock(forceOpen) {
  const next = typeof forceOpen === "boolean" ? forceOpen : !state.logDockOpen;
  setLogDockOpen(next);
}

function setAutoDockOpen(open) {
  state.autoDockOpen = open;
  if (!autoDockPanel || !autoDockToggle) return;
  autoDockPanel.classList.toggle("is-open", open);
  autoDockPanel.setAttribute("aria-hidden", String(!open));
  autoDockToggle.setAttribute("aria-expanded", String(open));
  autoDock?.classList.toggle("open", open);
  if (open) {
    fetchAutoStatus().catch(() => {});
    ensureAutoPolling();
    ensureAutoCountdown();
    tickAutoCountdown();
  } else if (!(state.autoScheduler && state.autoScheduler.state === "running")) {
    stopAutoPolling();
  }
}

function toggleAutoDock(forceOpen) {
  const next = typeof forceOpen === "boolean" ? forceOpen : !state.autoDockOpen;
  setAutoDockOpen(next);
}

function formatAutoCountdown(targetUnix) {
  if (!targetUnix) return "—";
  const nowSec = Math.floor((Date.now() + state.autoServerSkewMs) / 1000);
  const diff = Math.max(0, Number(targetUnix) - nowSec);
  const hours = Math.floor(diff / 3600);
  const minutes = Math.floor((diff % 3600) / 60);
  const seconds = diff % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function resolveNextAutoTask(status) {
  const pipeline = status?.refresh_pipeline;
  if (pipeline?.active && Array.isArray(pipeline.steps)) {
    const current = pipeline.steps.find((step) => step.status === "active" || step.status === "waiting");
    if (current?.label) return sanitizeUserText(current.label);
    const pending = pipeline.steps.find((step) => step.status === "pending");
    if (pending?.label) return sanitizeUserText(pending.label);
  }
  const slot = status?.next_slot || {};
  if (slot.action_label) return sanitizeUserText(slot.action_label);
  if (slot.label) return sanitizeUserText(slot.label);
  return "—";
}

function resolveAutoJobText(status) {
  const jobProbe = status?.job_probe || {};
  const jobState = String(jobProbe.job_state || "idle");
  const jobLabel = sanitizeUserText(jobProbe.job_label || jobProbe.job_action || "");
  if (jobState === "running") {
    return jobLabel ? `运行中 · ${jobLabel}` : "运行中";
  }
  if (jobState === "idle") return "空闲";
  if (jobState === "success") return jobLabel ? `已完成 · ${jobLabel}` : "已完成";
  if (jobState === "error") return jobLabel ? `出错 · ${jobLabel}` : "出错";
  return jobLabel || jobState || "—";
}

function renderAutoPipeline(pipeline) {
  if (!autoDockPipeline) return;
  const steps = Array.isArray(pipeline?.steps) ? pipeline.steps : [];
  if (!steps.length) {
    autoDockPipeline.innerHTML = "";
    return;
  }
  autoDockPipeline.innerHTML = steps
    .map((step, index) => {
      const label = sanitizeUserText(step.label || step.action || "");
      const status = step.status || "pending";
      const stepIndex = Number.isFinite(step.index) ? Number(step.index) + 1 : index + 1;
      return `<div class="auto-dock-step" data-status="${status}" data-index="${stepIndex}"><span class="auto-dock-step-label">${label}</span></div>`;
    })
    .join("");
}

function renderAutoDock(status) {
  if (!status) return;
  state.autoScheduler = status;
  if (status.server_now_unix) {
    state.autoServerSkewMs = status.server_now_unix * 1000 - Date.now();
  }

  const schedulerState = String(status.state || "idle");
  const stateLabel = sanitizeUserText(status.state_label || status.message || "尚未启动");
  const message = sanitizeUserText(status.message || "");
  const phase = sanitizeUserText(status.current_phase || "—");
  const hint = sanitizeUserText(status.next_hint || status.next_slot?.hint || "—");

  if (autoDockStatus) {
    autoDockStatus.textContent = message || stateLabel;
  }
  if (autoDockPhase) {
    autoDockPhase.textContent = phase;
  }
  if (autoDockHint) {
    autoDockHint.textContent = hint;
  }
  if (autoDockNextTask) {
    autoDockNextTask.textContent = resolveNextAutoTask(status);
  }
  if (autoDockJob) {
    autoDockJob.textContent = resolveAutoJobText(status);
  }
  tickAutoCountdown();
  renderAutoPipeline(status.refresh_pipeline);

  const running = schedulerState === "running";
  const fatal = schedulerState === "fatal";

  autoDock?.classList.toggle("fatal", fatal);
  if (autoDockBadge) {
    autoDockBadge.hidden = !running && !fatal;
    autoDockBadge.textContent = fatal ? "已停机" : "运行中";
    autoDockBadge.classList.toggle("fatal", fatal);
  }
  if (autoDockFatal) {
    autoDockFatal.hidden = !fatal;
  }
  if (autoDockFatalText) {
    autoDockFatalText.textContent = sanitizeUserText(status.fatal_error || "");
  }
  if (autoDockStartBtn) {
    autoDockStartBtn.hidden = running || fatal;
  }
  if (autoDockStopBtn) {
    autoDockStopBtn.hidden = !running;
  }
  if (autoDockRestartBtn) {
    autoDockRestartBtn.hidden = !fatal;
  }

  if (running || state.autoDockOpen) {
    ensureAutoPolling();
    ensureAutoCountdown();
  } else {
    stopAutoPolling();
  }
}

function tickAutoCountdown() {
  const status = state.autoScheduler;
  if (!autoDockCountdown) return;
  autoDockCountdown.textContent = formatAutoCountdown(status?.next_slot?.at_unix);
}

function ensureAutoCountdown() {
  if (state.autoCountdownTimer) return;
  state.autoCountdownTimer = window.setInterval(tickAutoCountdown, 1000);
}

function ensureAutoPolling() {
  if (!state.autoPollTimer) {
    state.autoPollTimer = window.setInterval(() => {
      fetchAutoStatus().catch(() => {});
    }, 2000);
  }
  ensureAutoCountdown();
}

function stopAutoPolling() {
  if (state.autoPollTimer) {
    window.clearInterval(state.autoPollTimer);
    state.autoPollTimer = null;
  }
  if (state.autoCountdownTimer) {
    window.clearInterval(state.autoCountdownTimer);
    state.autoCountdownTimer = null;
  }
}

async function fetchAutoStatus() {
  const status = await fetchJSON("/api/auto/status");
  renderAutoDock(status);
  return status;
}

async function startAutoScheduler() {
  await fetchJSON("/api/auto/start", { method: "POST" });
  await fetchAutoStatus();
  ensureAutoPolling();
  showToast("定时调度已启动", "success");
}

async function stopAutoScheduler() {
  const ok = window.confirm("停止调度只会停下定时点击监视器，不会取消正在运行的抽奖任务。确定停止？");
  if (!ok) return;
  await fetchJSON("/api/auto/stop", { method: "POST" });
  await fetchAutoStatus();
  showToast("定时调度已停止", "info");
}

function bindAutoDock() {
  autoDockToggle?.addEventListener("click", () => toggleAutoDock());
  document.getElementById("auto-dock-collapse")?.addEventListener("click", () => toggleAutoDock(false));
  autoDockStartBtn?.addEventListener("click", () => {
    autoDockStartBtn.disabled = true;
    startAutoScheduler()
      .catch((error) => showToast(sanitizeUserText(error.message || error) || "启动失败", "error"))
      .finally(() => {
        autoDockStartBtn.disabled = false;
      });
  });
  autoDockRestartBtn?.addEventListener("click", () => {
    autoDockRestartBtn.disabled = true;
    startAutoScheduler()
      .catch((error) => showToast(sanitizeUserText(error.message || error) || "重启失败", "error"))
      .finally(() => {
        autoDockRestartBtn.disabled = false;
      });
  });
  autoDockStopBtn?.addEventListener("click", () => {
    autoDockStopBtn.disabled = true;
    stopAutoScheduler()
      .catch((error) => showToast(sanitizeUserText(error.message || error) || "停止失败", "error"))
      .finally(() => {
        autoDockStopBtn.disabled = false;
      });
  });
}

function participateStepLabelsForType(lotteryType) {
  return lotteryType === "预约抽奖" ? ["预约"] : [...PARTICIPATE_STEP_LABELS];
}

function findTripleTargetForLane(lane, job) {
  const targets = job?.result?.targets || state.tripleTargets?.items || [];
  const laneKey = String(lane?.idPart || "").trim();
  if (!laneKey) return null;
  return (
    targets.find((item) => {
      const title = String(item?.activity_title || "").trim();
      const dynamicId = String(item?.dynamic_id || "").trim();
      return (
        title === laneKey ||
        dynamicId === laneKey ||
        dynamicId.endsWith(laneKey) ||
        laneKey.endsWith(dynamicId.slice(-6))
      );
    }) || null
  );
}

function participateActiveStepIndex(status, labelCount) {
  const text = String(status || "");
  if (PARTICIPATE_DONE_KEYWORDS.some((keyword) => text.includes(keyword))) {
    return labelCount;
  }
  const match = text.match(/（\s*(\d+)\s*\/\s*(\d+)\s*）/);
  if (match) {
    const step = Number(match[1]);
    if (step > 0) return Math.min(step - 1, Math.max(0, labelCount - 1));
  }
  if (PARTICIPATE_PENDING_KEYWORDS.some((keyword) => text.includes(keyword)) || text.includes("检查")) {
    return -1;
  }
  const reserveIndex = text.includes("预约") ? 0 : -1;
  for (let index = 0; index < PARTICIPATE_STEP_LABELS.length; index += 1) {
    if (text.includes(PARTICIPATE_STEP_LABELS[index])) return Math.min(index, labelCount - 1);
  }
  return reserveIndex;
}

function buildPipelineStepsHtml(labels, activeIndex, options = {}) {
  const failed = Boolean(options.failed);
  return labels
    .map((label, index) => {
      let stepState = "pending";
      if (failed && activeIndex >= 0) {
        if (index < activeIndex) stepState = "done";
        else if (index === activeIndex) stepState = "failed";
      } else if (activeIndex >= labels.length) {
        stepState = "done";
      } else if (activeIndex >= 0) {
        if (index < activeIndex) stepState = "done";
        else if (index === activeIndex) stepState = "active";
      }
      const connectorDone = stepState === "done" || (activeIndex >= 0 && index < activeIndex);
      const connector =
        index < labels.length - 1
          ? `<span class="pipeline-connector ${connectorDone ? "done" : ""}"></span>`
          : "";
      const dotContent = stepState === "done" ? "✓" : stepState === "failed" ? "×" : index + 1;
      return `
        <div class="pipeline-node ${stepState}">
          <span class="pipeline-dot" aria-hidden="true">${dotContent}</span>
          <span class="pipeline-label">${escapeHtml(label)}</span>
        </div>${connector}`;
    })
    .join("");
}

function renderPipelineSteps(labels, activeIndex) {
  if (!progressSteps) return;
  progressSteps.hidden = false;
  progressSteps.classList.remove("is-triple");
  progressSteps.innerHTML = buildPipelineStepsHtml(labels, activeIndex);
}

function buildJobKey(job) {
  return `${job?.action || ""}:${job?.started_at || ""}`;
}

function resetJobProgressTracking(job) {
  const nextKey = buildJobKey(job);
  if (state.activeJobKey !== nextKey) {
    state.activeJobKey = nextKey;
    state.smoothJobPercent = 0;
    if (progressBanner) progressBanner.dataset.percent = "0";
  }
}

function parseTripleProgressLanes(message) {
  return String(message || "")
    .split("|")
    .map((part) => part.trim())
    .filter(Boolean)
    .map((segment) => {
      const colonIndex = segment.indexOf(":");
      const idPart = colonIndex >= 0 ? segment.slice(0, colonIndex).trim() : segment;
      const status = colonIndex >= 0 ? segment.slice(colonIndex + 1).trim() : "等待中";
      return { idPart, status: status || "等待中" };
    });
}

function commentFailureOptional(action) {
  if (!action || action.action !== "comment" || action.ok) return false;
  const detail = String(action.detail || "");
  return COMMENT_OPTIONAL_PATTERNS.some((pattern) => pattern.test(detail));
}

function participationSucceeded(actions, lotteryType) {
  const actionMap = new Map((actions || []).map((item) => [item?.action, item]));
  if (lotteryType === "预约抽奖") {
    const reserve = actionMap.get("reserve");
    return reserve?.ok === true;
  }
  if (lotteryType === "互动抽奖") {
    if (!INTERACT_REQUIRED_ACTIONS.every((name) => actionMap.get(name)?.ok === true)) return false;
    const comment = actionMap.get("comment");
    if (comment && comment.ok !== true && !commentFailureOptional(comment)) return false;
    return true;
  }
  if (lotteryType === "转发抽奖") {
    return FORWARD_REQUIRED_ACTIONS.every((name) => actionMap.get(name)?.ok === true);
  }
  return (actions || []).every((item) => item?.ok !== false);
}

function payloadJoinedSuccess(payload) {
  if (payload?.status !== "joined") return false;
  const actions = payload?.actions || [];
  if (!actions.length) return false;
  return participationSucceeded(actions, payload?.lottery_type || "");
}

function summarizeTripleResult(result) {
  const items = result?.items || [];
  let joined = 0;
  let failed = 0;
  for (const item of items) {
    if (payloadJoinedSuccess(item)) joined += 1;
    else failed += 1;
  }
  return { joined, failed, total: items.length };
}

function renderActionChips(actions) {
  if (!actions?.length) return "";
  return `
    <div class="participation-result-steps">
      ${actions
        .map((item) => {
          const label = ACTION_LABELS[item?.action] || item?.action || "步骤";
          let stepState = "skipped";
          let icon = "○";
          if (item?.ok === true) {
            stepState = "done";
            icon = "✓";
          } else if (item?.ok === false) {
            stepState = "failed";
            icon = "×";
          }
          return `<span class="participation-result-step ${stepState}">${icon} ${escapeHtml(label)}</span>`;
        })
        .join("")}
    </div>`;
}

function formatJobProgressDisplay(job) {
  const step = Number(job.progress_step) || 0;
  const total = Number(job.progress_total) || 0;
  const percent = calcJobProgressPercent(job);
  if (job.action === "participate" || job.action === "participate_triple") {
    if (total > 0) {
      return { percent, value: `${step}/${total}`, suffix: " 步", showPercentSuffix: false };
    }
    return { percent: 0, value: "0", suffix: "", showPercentSuffix: false };
  }
  return { percent, value: String(percent), suffix: "%", showPercentSuffix: true };
}

function classifyLaneStatus(status) {
  const text = String(status || "");
  if (PARTICIPATE_FAIL_KEYWORDS.some((keyword) => text.includes(keyword))) return "failed";
  if (PARTICIPATE_DONE_KEYWORDS.some((keyword) => text.includes(keyword))) return "done";
  if (PARTICIPATE_PENDING_KEYWORDS.some((keyword) => text.includes(keyword))) return "pending";
  if (PARTICIPATE_ACTIVE_KEYWORDS.some((keyword) => text.includes(keyword))) return "active";
  return "pending";
}

function summarizeTripleProgressLanes(lanes) {
  const doneCount = lanes.filter((lane) => classifyLaneStatus(lane.status) === "done").length;
  const activeLanes = lanes.filter((lane) => classifyLaneStatus(lane.status) === "active");
  const failedCount = lanes.filter((lane) => classifyLaneStatus(lane.status) === "failed").length;
  return { doneCount, activeLanes, failedCount };
}

function formatProgressTitle(job) {
  if (job.action === "participate") return "正在参与活动";
  if (job.action === "participate_triple") {
    const lanes = parseTripleProgressLanes(job.progress_message);
    const count = lanes.length || Number(job.result?.targets?.length) || 3;
    return `三连参与 · 并行 ${count} 个活动`;
  }
  return job.label || "任务运行中…";
}

function formatProgressDetail(job) {
  if (job.action === "participate") {
    const message = sanitizeUserText(job.progress_message || job.message || "");
    if (message && !message.includes("|")) return message;
    const step = Number(job.progress_step) || 0;
    const total = Number(job.progress_total) || PARTICIPATE_STEP_LABELS.length;
    const labels = total === 1 ? ["预约"] : PARTICIPATE_STEP_LABELS.slice(0, total);
    if (step > 0 && step <= labels.length) return `当前步骤：${labels[step - 1]}`;
    return "准备开始参与…";
  }
  if (job.action === "participate_triple") {
    const lanes = parseTripleProgressLanes(job.progress_message);
    if (!lanes.length) return "并行处理中，请稍候…";
    const { doneCount, activeLanes, failedCount } = summarizeTripleProgressLanes(lanes);
    if (failedCount > 0) {
      return `已停止 ${doneCount}/${lanes.length} 完成 · ${failedCount} 个失败`;
    }
    if (activeLanes.length > 1) {
      return `并行进行中 ${doneCount}/${lanes.length} · ${activeLanes.length} 个活动同时执行`;
    }
    if (activeLanes.length === 1) {
      return `并行进行中 ${doneCount}/${lanes.length} · 当前：…${activeLanes[0].idPart} ${activeLanes[0].status}`;
    }
    return `并行进行中 ${doneCount}/${lanes.length} 个活动已完成步骤`;
  }
  return sanitizeUserText(job.progress_message || job.message || "请稍候，任务在后台执行中");
}

function hideParticipationResult(immediate = false) {
  if (state.jobResultTimer) {
    window.clearTimeout(state.jobResultTimer);
    state.jobResultTimer = null;
  }
  if (!jobResultBanner || jobResultBanner.hidden) return;

  if (immediate) {
    jobResultBanner.hidden = true;
    jobResultBanner.classList.remove("is-visible", "is-hiding");
    return;
  }

  jobResultBanner.classList.add("is-hiding");
  jobResultBanner.classList.remove("is-visible");
  state.jobResultTimer = window.setTimeout(() => {
    jobResultBanner.hidden = true;
    jobResultBanner.classList.remove("is-hiding");
    state.jobResultTimer = null;
  }, JOB_RESULT_EXIT_MS);
}

function scheduleParticipationResultDismiss(delayMs = JOB_RESULT_AUTO_DISMISS_MS) {
  if (state.jobResultTimer) {
    window.clearTimeout(state.jobResultTimer);
  }
  state.jobResultTimer = window.setTimeout(() => hideParticipationResult(), delayMs);
}

function restartParticipationResultProgress() {
  if (!jobResultProgress) return;
  jobResultProgress.style.animation = "none";
  void jobResultProgress.offsetWidth;
  jobResultProgress.style.animation = "";
}

function renderParticipationStepResults(result) {
  const actions = result?.actions || [];
  if (!actions.length) {
    const message = sanitizeUserText(result?.message || "");
    if (result?.status === "joined" && !payloadJoinedSuccess(result)) {
      return `<p class="caption">参与未完成：${escapeHtml(message || "请查看任务日志")}</p>`;
    }
    return message
      ? `<p class="caption">${escapeHtml(message)}</p>`
      : `<p class="caption">暂无步骤明细，可在任务日志中查看详情。</p>`;
  }
  return renderActionChips(actions);
}

function renderTripleParticipationResults(result) {
  const targets = result?.targets || [];
  const items = result?.items || [];
  const itemMap = new Map(items.map((item) => [String(item?.dynamic_id || ""), item]));
  const rows = (targets.length ? targets : items).map((entry) => {
    const dynamicId = String(entry?.dynamic_id || "");
    const payload = itemMap.get(dynamicId) || entry;
    const title = payload?.activity_title || entry?.activity_title || dynamicId || "未知活动";
    const lotteryType = payload?.lottery_type || entry?.lottery_type || "";
    const actions = payload?.actions || [];
    const succeeded = payloadJoinedSuccess(payload);
    const status = String(payload?.status || "");
    let statusLabel = "未完成";
    let statusClass = "skipped";
    if (succeeded) {
      statusLabel = "成功";
      statusClass = "success";
    } else if (status === "failed" || (status === "joined" && !payloadJoinedSuccess(payload))) {
      statusLabel = "失败";
      statusClass = "failed";
    }
    const message = sanitizeUserText(payload?.message || "");
    return `
      <div class="participation-result-item">
        <div class="participation-result-item-title" title="${escapeHtml(title)}">${escapeHtml(truncateText(title, 42))}</div>
        ${lotteryType ? `<span class="participation-result-item-meta">${escapeHtml(lotteryType)}</span>` : ""}
        <span class="participation-result-status ${statusClass}">${statusLabel}</span>
        ${actions.length ? renderActionChips(actions) : message ? `<p class="caption">${escapeHtml(message)}</p>` : ""}
      </div>`;
  });
  if (!rows.length) {
    return `<p class="caption">暂无活动结果，可在任务日志中查看详情。</p>`;
  }
  return `<div class="participation-result-list">${rows.join("")}</div>`;
}

function showParticipationResult(job) {
  if (!jobResultBanner || (job.action !== "participate" && job.action !== "participate_triple")) return;
  if (job.result?.skipped) return;
  hideParticipationResult(true);

  const result = job.result || {};
  const isTriple = job.action === "participate_triple";
  let joined = 0;
  let failed = 0;
  let total = 1;
  if (isTriple) {
    const summary = summarizeTripleResult(result);
    joined = summary.joined;
    failed = summary.failed;
    total = summary.total;
  } else {
    joined = payloadJoinedSuccess(result) ? 1 : 0;
    failed = joined ? 0 : 1;
    total = 1;
  }

  let tone = "is-error";
  let icon = "!";
  let title = "参与未完成";
  const allSucceeded =
    job.state === "success" && total > 0 && joined >= total && failed === 0;
  if (allSucceeded) {
    tone = "is-success";
    icon = "✓";
    title = isTriple ? "三连参与完成" : "参与成功";
  } else if (joined > 0) {
    tone = "is-partial";
    icon = "◐";
    title = isTriple ? "三连参与部分完成" : "参与部分完成";
  }

  jobResultBanner.className = `job-result-banner ${tone}`;
  jobResultBanner.hidden = false;
  if (jobResultIcon) jobResultIcon.textContent = icon;
  if (jobResultEyebrow) jobResultEyebrow.textContent = isTriple ? "三连参与结果" : "参与结果";
  if (jobResultTitle) jobResultTitle.textContent = title;
  if (jobResultSummary) {
    const fallback = joined > 0 ? "请查看下方各活动执行情况" : "请查看下方步骤详情";
    jobResultSummary.textContent = sanitizeUserText(job.message) || fallback;
  }
  if (jobResultBody) {
    jobResultBody.innerHTML = isTriple
      ? renderTripleParticipationResults(result)
      : renderParticipationStepResults(result);
  }

  jobResultBanner.classList.remove("is-hiding");
  void jobResultBanner.offsetWidth;
  jobResultBanner.classList.add("is-visible");
  restartParticipationResultProgress();
  scheduleParticipationResultDismiss();
}

function renderTripleParticipateProgress(job) {
  if (!progressSteps) return;
  progressSteps.hidden = false;
  progressSteps.classList.add("is-triple");
  const lanes = parseTripleProgressLanes(job.progress_message);
  if (!lanes.length) {
    progressSteps.innerHTML = `<p class="caption">三连参与并行进行中…</p>`;
    return;
  }
  progressSteps.innerHTML = `
    <div class="triple-progress-stack">
      ${lanes
        .map((lane, index) => {
          const target = findTripleTargetForLane(lane, job);
          const lotteryType = target?.lottery_type || "";
          const labels = participateStepLabelsForType(lotteryType);
          const laneState = classifyLaneStatus(lane.status);
          const failed = laneState === "failed";
          const activeIndex = participateActiveStepIndex(lane.status, labels.length);
          const title = truncateText(target?.activity_title || lane.idPart, 36);
          return `
            <section class="triple-progress-lane is-${laneState}">
              <div class="triple-progress-lane-head">
                <span class="triple-progress-index">#${index + 1}</span>
                <div class="triple-progress-lane-copy">
                  <span class="triple-progress-title">${escapeHtml(title)}</span>
                  <span class="triple-progress-status">${escapeHtml(lane.status)}</span>
                </div>
              </div>
              <div class="progress-pipeline triple-lane-pipeline">
                ${buildPipelineStepsHtml(labels, activeIndex, { failed })}
              </div>
            </section>`;
        })
        .join("")}
    </div>`;
}

function renderParticipateSteps(job) {
  if (!progressSteps) return;
  if (job.state === "running" && job.action === "participate_triple") {
    renderTripleParticipateProgress(job);
    return;
  }
  if (job.state !== "running" || job.action !== "participate") {
    if (job.state === "running" && isRefreshPipelineAction(job.action)) {
      renderRefreshAllPipeline(job);
      return;
    }
    if (job.state === "running" && job.action === "refresh_watch") {
      renderRefreshWatchPipeline(job);
      return;
    }
    progressSteps.hidden = true;
    progressSteps.innerHTML = "";
    progressSteps.classList.remove("is-triple");
    return;
  }
  const total = Number(job.progress_total) || PARTICIPATE_STEP_LABELS.length;
  const current = Number(job.progress_step) || 0;
  const labels = total === 1 ? ["预约"] : PARTICIPATE_STEP_LABELS.slice(0, total);
  const activeIndex = Math.max(0, Math.min(labels.length - 1, current > 0 ? current - 1 : 0));
  renderPipelineSteps(labels, activeIndex);
}

function refreshAllDataSourceCount(job) {
  const total = Number(job.progress_total) || REFRESH_ALL_DS_COUNT + REFRESH_ALL_PIPELINE_SUBSTEPS;
  return Math.max(1, total - REFRESH_ALL_PIPELINE_SUBSTEPS);
}

function refreshAllPipelinePhaseFromMessage(message) {
  const text = String(message || "");
  if (/跳过.*流水线|均无新专栏|无新专栏/.test(text)) return 3;
  if (/入库|落库|写入活动库/.test(text)) return 3;
  if (/详情进度|活动详情/.test(text)) return 2;
  if (/分类|新链接/.test(text)) return 1;
  return null;
}

function refreshAllSubprogressRatio(message) {
  const match = String(message || "").match(/\((\d+)\s*\/\s*(\d+)\)/);
  if (!match) return null;
  return Number(match[1]) / Math.max(1, Number(match[2]));
}

function refreshAllPipelinePhase(step, dsCount, message) {
  if (step > dsCount) {
    const fromMessage = refreshAllPipelinePhaseFromMessage(message);
    if (fromMessage !== null) return fromMessage;
  }
  if (step <= dsCount) return 0;
  if (step === dsCount + 1) return 1;
  if (step === dsCount + 2) return 2;
  return 3;
}

function renderRefreshAllPipeline(job) {
  if (!progressSteps) return;
  const step = Number(job.progress_step) || 0;
  const dsCount = refreshAllDataSourceCount(job);
  const message = job.progress_message || job.message || "";
  renderPipelineSteps(REFRESH_ALL_PIPELINE, refreshAllPipelinePhase(step, dsCount, message));
}

function renderRefreshWatchPipeline(job) {
  if (!progressSteps) return;
  progressSteps.hidden = false;
  const step = Number(job.progress_step) || 0;
  let phase = 0;
  if (step <= 1) phase = 0;
  else if (step === 2) phase = 1;
  else if (step === 3) phase = 2;
  else phase = 3;
  renderPipelineSteps(REFRESH_WATCH_PIPELINE, phase);
}

function calcJobProgressPercent(job) {
  const total = Number(job.progress_total) || 0;
  const step = Number(job.progress_step) || 0;
  if (total <= 0) return 8;
  if (isRefreshPipelineAction(job.action)) {
    const dsCount = refreshAllDataSourceCount(job);
    const detail = String(job.progress_message || job.message || "");
    if (step >= total) return 100;
    if (/跳过.*流水线|均无新专栏|无新专栏/.test(detail)) return 100;
    if (step <= 0) return 6;
    if (step <= dsCount) return Math.round(10 + (step / dsCount) * 38);
    const phase = refreshAllPipelinePhase(step, dsCount, detail);
    const ratio = refreshAllSubprogressRatio(detail);
    if (phase === 1) {
      return ratio != null ? Math.min(68, Math.round(50 + ratio * 18)) : 52;
    }
    if (phase === 2) {
      return ratio != null ? Math.min(90, Math.round(70 + ratio * 18)) : 74;
    }
    if (phase === 3) return 100;
  }
  if (job.action === "refresh_watch") {
    if (step <= 0) return 6;
    if (step === 1) {
      const detail = String(job.progress_message || "");
      const match = detail.match(/(\d+)\s*\/\s*(\d+)/);
      if (match) {
        const ratio = Number(match[1]) / Math.max(1, Number(match[2]));
        return Math.min(42, Math.round(10 + ratio * 32));
      }
      return 18;
    }
    if (step === 2) {
      const detail = String(job.progress_message || "");
      const match = detail.match(/\((\d+)\s*\/\s*(\d+)\)/);
      if (match) {
        const ratio = Number(match[1]) / Math.max(1, Number(match[2]));
        return Math.min(68, Math.round(46 + ratio * 20));
      }
      return 50;
    }
    if (step === 3) {
      const detail = String(job.progress_message || "");
      const match = detail.match(/\((\d+)\s*\/\s*(\d+)\)/);
      if (match) {
        const ratio = Number(match[1]) / Math.max(1, Number(match[2]));
        return Math.min(90, Math.round(72 + ratio * 16));
      }
      return 76;
    }
    if (step >= 4) return 100;
  }
  if (job.action === "participate" || job.action === "participate_triple") {
    if (total <= 0) return 0;
    return Math.max(0, Math.min(100, Math.round((step / total) * 100)));
  }
  return Math.max(0, Math.min(100, Math.round((step / total) * 100)));
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
    { label: "上次新入库", value: summary.new_count ?? 0 },
  ];
  statsGrid.innerHTML = cards
    .map(
      (card, index) => `
      <article class="stat-card is-entering" style="--card-delay:${index * 55}ms">
        <p class="stat-label">${card.label}</p>
        <p class="stat-value">${card.value}</p>
      </article>`
    )
    .join("");
}

function formatAccountStat(value, loggedIn, loading = false) {
  if (value === null || value === undefined) {
    if (!loggedIn) return "—";
    return loading ? "…" : 0;
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
    const networkError = Boolean(account.network_error);
    const cookieSaved = Boolean(account.cookie_saved);
    const title = networkError && cookieSaved ? "暂时无法连接 B 站" : "未登录";
    const subtitle = networkError && cookieSaved && account.mid
      ? `UID ${escapeHtml(account.mid)} · 本地 Cookie 已保存`
      : "";
    const emptyHtml = `
      <div class="account-empty">
        <div class="account-avatar account-avatar-fallback account-avatar-lg"></div>
        <div>
          <h3>${escapeHtml(title)}</h3>
          ${subtitle ? `<p class="caption">${subtitle}</p>` : ""}
          <p>${escapeHtml(account.message || "请使用侧边栏扫码登录")}</p>
          ${renderSetupChecklist()}
          <span class="account-status warn">${networkError && cookieSaved ? "网络恢复后点击「刷新账号」" : "需完成登录、LLM 配置与连接测试"}</span>
        </div>
      </div>`;
    if (accountHero) accountHero.innerHTML = emptyHtml;
    if (sidebarAccountCard) {
      const sidebarName = networkError && cookieSaved
        ? (account.uname || `UID ${account.mid || "—"}`)
        : "未登录";
      const sidebarSub = networkError && cookieSaved ? "网络异常" : "扫码登录后开始";
      sidebarAccountCard.innerHTML = `
        <div class="sidebar-account-mini" title="${escapeHtml(account.message || "请扫码登录")}">
          <div class="account-avatar account-avatar-fallback"></div>
          <div class="sidebar-account-text sidebar-fade">
            <p class="sidebar-account-name">${escapeHtml(sidebarName)}</p>
            <p class="sidebar-account-sub">${escapeHtml(sidebarSub)}</p>
          </div>
        </div>`;
    }
    updateWatchUserFormState();
    if (state.watchUsers) renderWatchUsersPanel(state.watchUsers);
    return;
  }

  const avatar = account.face
    ? `<img class="account-avatar account-avatar-lg" src="${escapeHtml(account.face)}" alt="头像" referrerpolicy="no-referrer" crossorigin="anonymous" />`
    : `<div class="account-avatar account-avatar-fallback account-avatar-lg"></div>`;
  const atNotifyUrl = account.at_notify_url || "https://message.bilibili.com/#/notify/at";
  const extrasLoading = Boolean(account.extras_loading);
  const atUnread = Number(formatAccountStat(account.unread_at, loggedIn, extrasLoading)) || 0;
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
        <div class="sidebar-account-text sidebar-fade">
          <p class="sidebar-account-name">${escapeHtml(account.uname || "B站用户")}</p>
          <p class="sidebar-account-sub">UID ${escapeHtml(account.mid || "—")}</p>
        </div>
      </div>`;
  }
  updateWatchUserFormState();
  if (state.watchUsers) renderWatchUsersPanel(state.watchUsers);
}

async function loadAccount() {
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

async function loadAccountExtras() {
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

function closeLogoutConfirmModal() {
  if (!logoutConfirmModal) return;
  logoutConfirmModal.hidden = true;
  document.body.classList.remove("modal-open");
}

function requestLogoutConfirm() {
  return new Promise((resolve) => {
    if (!logoutConfirmModal || !logoutConfirmCancel || !logoutConfirmYes) {
      resolve(window.confirm("确认退出登录？退出后需要重新扫码登录。"));
      return;
    }

    const cleanup = () => {
      closeLogoutConfirmModal();
      logoutConfirmCancel.removeEventListener("click", onCancel);
      logoutConfirmYes.removeEventListener("click", onConfirm);
      logoutConfirmBackdrop?.removeEventListener("click", onCancel);
      document.removeEventListener("keydown", onKeyDown);
    };

    const onCancel = () => {
      cleanup();
      resolve(false);
    };

    const onConfirm = () => {
      cleanup();
      resolve(true);
    };

    const onKeyDown = (event) => {
      if (event.key === "Escape") onCancel();
    };

    logoutConfirmModal.hidden = false;
    document.body.classList.add("modal-open");
    logoutConfirmCancel.addEventListener("click", onCancel);
    logoutConfirmYes.addEventListener("click", onConfirm);
    logoutConfirmBackdrop?.addEventListener("click", onCancel);
    document.addEventListener("keydown", onKeyDown);
    logoutConfirmCancel.focus();
  });
}

async function loadSettings() {
  const settings = await fetchJSON("/api/settings");
  state.settings = settings;
  renderParticipateSettings(settings);
  renderLlmSettingsForm(settings);
  return settings;
}

function getParticipateTextDefaults(settings) {
  return {
    custom: settings?.default_participate_text || "好运连连！",
    fallback: settings?.default_participate_fallback_text || settings?.default_participate_text || "好运连连！",
  };
}

function getParticipateTextForMode(settings, mode) {
  const defaults = getParticipateTextDefaults(settings || {});
  if (mode === "random_comment") {
    return settings?.participate_fallback_text || defaults.fallback;
  }
  return settings?.participate_text || defaults.custom;
}

function updateParticipateTextUI(mode) {
  const isRandom = mode === "random_comment";
  const label = document.getElementById("participate-text-label");
  const hint = document.getElementById("participate-text-hint");
  const note = document.getElementById("participate-random-note");
  const saveBtn = document.getElementById("save-participate-text");
  const resetBtn = document.getElementById("reset-participate-text");
  const desc = document.getElementById("participate-settings-desc");
  const fields = document.getElementById("participate-text-fields");
  if (label) label.textContent = isRandom ? "兜底文案" : "当前文案";
  if (hint) {
    hint.textContent = isRandom ? "评论不足时使用 · 最多 233 字" : "最多 233 字";
  }
  if (note) note.hidden = !isRandom;
  if (fields) fields.classList.toggle("participate-text-fields--random", isRandom);
  if (saveBtn) saveBtn.textContent = isRandom ? "保存兜底文案" : "保存文案";
  if (resetBtn) resetBtn.textContent = isRandom ? "恢复默认兜底" : "恢复默认";
  if (desc) {
    desc.innerHTML = isRandom
      ? "参与时从活动评论区<strong>第 6～65 条</strong>中随机抽取一条，作为转发与评论内容。"
      : '用于转发与评论，建议格式：<strong>@好友昵称 + 一句话</strong>。例如 <code>@小明 好运连连！</code>';
  }
}

function renderParticipateSettings(settings) {
  const mode =
    settings?.participate_text_mode || settings?.default_participate_text_mode || "custom";
  const defaults = getParticipateTextDefaults(settings);
  const input = document.getElementById("participate-text-input");
  if (input) {
    input.value = getParticipateTextForMode(settings, mode);
    input.placeholder =
      mode === "random_comment" ? defaults.fallback : defaults.custom;
  }
  document.querySelectorAll("[data-participate-mode]").forEach((button) => {
    const active = button.dataset.participateMode === mode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
  updateParticipateTextUI(mode);
}

async function saveParticipateTextMode(mode) {
  if (!isLoggedIn()) {
    showToast("请先扫码登录", "info", "登录后才能修改参与文案模式");
    return false;
  }
  const result = await fetchJSON("/api/settings/participate-text", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ participate_text_mode: mode }),
  });
  if (state.settings) {
    if (result.participate_text_mode) {
      state.settings.participate_text_mode = result.participate_text_mode;
    }
    if (result.participate_text) {
      state.settings.participate_text = result.participate_text;
    }
    if (result.participate_fallback_text) {
      state.settings.participate_fallback_text = result.participate_fallback_text;
    }
  }
  renderParticipateSettings(state.settings || { participate_text_mode: result.participate_text_mode || mode });
  const label = mode === "random_comment" ? "随机借用评论" : "自定义文案";
  setInlineFeedback(participateTextFeedback, `已切换为「${label}」`, "success");
  return true;
}

function bindParticipateSettings() {
  document.querySelectorAll("[data-participate-mode]").forEach((button) => {
    if (button.dataset.bound === "true") return;
    button.dataset.bound = "true";
    button.addEventListener("click", async () => {
      if (button.classList.contains("active")) return;
      const mode = button.dataset.participateMode || "custom";
      const originalDisabled = button.disabled;
      button.disabled = true;
      try {
        await saveParticipateTextMode(mode);
      } catch (error) {
        setInlineFeedback(participateTextFeedback, String(error.message || error), "error");
      } finally {
        button.disabled = originalDisabled;
      }
    });
  });
}

async function syncProjectState() {
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
  setButtonLoading(button, true, { label: "刷新中…" });
  setInlineFeedback(llmActionFeedback, "", "info");
  try {
    const result = await fetchJSON("/api/settings/llm");
    state.settings = { ...(state.settings || {}), llm: result.llm, setup_complete: result.setup_complete };
    renderLlmSettingsForm(state.settings);
    if (state.account) renderAccountViews(state.account);
    const detail = result.llm?.configured
      ? `${result.llm.model_name || "已配置"} · ${result.llm.api_key_hint || ""}`
      : "本地配置文件为空或未完整填写";
    setInlineFeedback(llmActionFeedback, `配置已刷新 · ${detail}`, "success");
  } catch (error) {
    setInlineFeedback(llmActionFeedback, String(error.message || error), "error");
    throw error;
  } finally {
    setButtonLoading(button, false);
  }
}

async function saveLlmSettings() {
  if (!isLoggedIn()) {
    setInlineFeedback(llmActionFeedback, "请先扫码登录后再保存", "info", { autoHide: false });
    return;
  }
  setInlineFeedback(llmActionFeedback, "", "info");
  try {
    const result = await fetchJSON("/api/settings/llm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(getLlmFormValues()),
    });
    state.settings = { ...(state.settings || {}), llm: result.llm, setup_complete: result.setup_complete };
    renderLlmSettingsForm(state.settings);
    if (state.account) renderAccountViews(state.account);
    setInlineFeedback(
      llmActionFeedback,
      `已保存 · ${result.llm.model_name || "已配置"} · ${result.llm.api_key_hint || ""}`,
      "success"
    );
  } catch (error) {
    setInlineFeedback(llmActionFeedback, String(error.message || error), "error");
    throw error;
  }
}

async function testLlmSettings() {
  if (!isLoggedIn()) {
    setInlineFeedback(llmActionFeedback, "请先扫码登录后再测试", "info", { autoHide: false });
    return;
  }
  const button = document.getElementById("test-llm-settings");
  setButtonLoading(button, true, { label: "测试中…" });
  setInlineFeedback(llmActionFeedback, "正在测试连接…", "info", { autoHide: false });
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
    setInlineFeedback(llmActionFeedback, result.message || "LLM 连接正常", "success");
  } catch (error) {
    setInlineFeedback(llmActionFeedback, String(error.message || error), "error");
    throw error;
  } finally {
    setButtonLoading(button, false);
  }
}

async function saveParticipateText() {
  if (!isLoggedIn()) {
    setInlineFeedback(participateTextFeedback, "请先扫码登录后再保存", "info", { autoHide: false });
    return;
  }
  const input = document.getElementById("participate-text-input");
  const button = document.getElementById("save-participate-text");
  const value = input?.value?.trim() || "";
  setButtonLoading(button, true, { label: "保存中…" });
  const mode = state.settings?.participate_text_mode || "custom";
  const payload =
    mode === "random_comment"
      ? { participate_fallback_text: value }
      : { participate_text: value };
  setInlineFeedback(participateTextFeedback, "", "info");
  try {
    const result = await fetchJSON("/api/settings/participate-text", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (input) {
      input.value = getParticipateTextForMode(
        {
          ...(state.settings || {}),
          participate_text: result.participate_text,
          participate_fallback_text: result.participate_fallback_text,
        },
        mode
      );
    }
    if (state.settings) {
      if (result.participate_text) state.settings.participate_text = result.participate_text;
      if (result.participate_fallback_text) {
        state.settings.participate_fallback_text = result.participate_fallback_text;
      }
    }
    const savedText =
      mode === "random_comment"
        ? result.participate_fallback_text || value
        : result.participate_text || value;
    setInlineFeedback(
      participateTextFeedback,
      mode === "random_comment" ? `兜底文案已保存：${savedText}` : `参与文案已保存：${savedText}`,
      "success"
    );
  } catch (error) {
    setInlineFeedback(participateTextFeedback, String(error.message || error), "error");
    throw error;
  } finally {
    setButtonLoading(button, false);
  }
}

async function resetParticipateText() {
  if (!isLoggedIn()) {
    setInlineFeedback(participateTextFeedback, "请先扫码登录后再恢复", "info", { autoHide: false });
    return;
  }
  const mode = state.settings?.participate_text_mode || "custom";
  const defaults = getParticipateTextDefaults(state.settings || {});
  const payload =
    mode === "random_comment"
      ? { participate_fallback_text: defaults.fallback }
      : { participate_text: defaults.custom };
  setInlineFeedback(participateTextFeedback, "", "info");
  try {
    const result = await fetchJSON("/api/settings/participate-text", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const input = document.getElementById("participate-text-input");
    if (input) {
      input.value = getParticipateTextForMode(
        {
          ...(state.settings || {}),
          participate_text: result.participate_text,
          participate_fallback_text: result.participate_fallback_text,
        },
        mode
      );
    }
    if (state.settings) {
      if (result.participate_text) state.settings.participate_text = result.participate_text;
      if (result.participate_fallback_text) {
        state.settings.participate_fallback_text = result.participate_fallback_text;
      }
    }
    const restoredText =
      mode === "random_comment"
        ? result.participate_fallback_text || defaults.fallback
        : result.participate_text || defaults.custom;
    setInlineFeedback(
      participateTextFeedback,
      mode === "random_comment" ? `已恢复默认兜底：${restoredText}` : `已恢复默认文案：${restoredText}`,
      "success"
    );
  } catch (error) {
    setInlineFeedback(participateTextFeedback, String(error.message || error), "error");
    throw error;
  }
}

function clearWatchMidError() {
  if (!watchAddMidInput || !watchAddMidError) return;
  watchAddMidInput.classList.remove("is-invalid");
  watchAddMidError.hidden = true;
  watchAddMidError.textContent = "";
}

function showWatchMidError(message) {
  if (!watchAddMidInput || !watchAddMidError) return;
  watchAddMidInput.classList.add("is-invalid");
  watchAddMidError.hidden = false;
  watchAddMidError.textContent = message;
}

function closeWatchUserConfirm(exceptChip = null) {
  document.querySelectorAll(".watch-user-chip.is-confirming").forEach((chip) => {
    if (chip !== exceptChip) chip.classList.remove("is-confirming");
  });
}

function renderWatchUsersPanel(data) {
  if (!data) return;
  state.watchUsers = data;
  const count = Number(data.count) || (data.users || []).length;
  if (watchMetricCount) watchMetricCount.textContent = String(count);
  if (watchMetricLinks) watchMetricLinks.textContent = String(data.last_scan_link_count ?? "—");
  if (watchUsersBadge) watchUsersBadge.textContent = `${count} 人`;
  if (watchLastSynced) watchLastSynced.textContent = formatUnixTimestamp(data.last_synced_at);
  if (watchNextWindow) {
    const window = data.next_window || {};
    watchNextWindow.textContent = formatWatchWindow(window.start, window.end);
  }
  if (watchWindowCap) {
    watchWindowCap.textContent = formatWindowDays(data.max_window_seconds);
  }
  updateWatchUserFormState();

  if (!watchUserGrid) return;
  const users = data.users || [];
  const canManage = isLoggedIn();
  if (!users.length) {
    watchUserGrid.innerHTML = `<p class="caption watch-user-empty">${canManage ? "暂无监控用户，可在上方添加" : "暂无监控用户"}</p>`;
    return;
  }
  watchUserGrid.innerHTML = users
    .map(
      (user) => `
      <article class="watch-user-chip" data-watch-mid="${escapeHtml(user.mid)}">
        <a class="watch-user-link" href="https://space.bilibili.com/${encodeURIComponent(user.mid)}/dynamic" target="_blank" rel="noopener" title="${escapeHtml(user.name)}">${escapeHtml(user.name)}</a>
        <span class="watch-user-mid">MID ${escapeHtml(user.mid)}</span>
        <div class="watch-user-actions">
          <button type="button" class="watch-user-remove" data-watch-remove="${escapeHtml(user.mid)}" aria-label="移除 ${escapeHtml(user.name)}" ${canManage ? "" : "disabled"} title="${canManage ? "移出监控名单" : "登录后可管理"}">×</button>
          <div class="watch-user-confirm-actions">
            <button type="button" class="btn btn-secondary btn-compact watch-user-confirm-yes" data-watch-confirm="${escapeHtml(user.mid)}">确认</button>
            <button type="button" class="watch-user-confirm-no" data-watch-cancel>取消</button>
          </div>
        </div>
      </article>`
    )
    .join("");
}

function updateWatchUserFormState() {
  const canManage = isLoggedIn();
  if (watchAddMidInput) watchAddMidInput.disabled = !canManage;
  if (watchAddBtn) {
    watchAddBtn.disabled = !canManage;
    watchAddBtn.title = canManage ? "" : "登录后可添加监控用户";
  }
}

async function loadWatchUsers() {
  try {
    const data = await fetchJSON("/api/watch-users");
    renderWatchUsersPanel(data);
    return data;
  } catch (error) {
    if (watchUserGrid) {
      watchUserGrid.innerHTML = `<p class="caption watch-user-empty">加载失败：${escapeHtml(String(error.message || error))}</p>`;
    }
    throw error;
  }
}

function parseWatchMidInput(raw) {
  const text = String(raw || "").trim();
  if (!/^\d+$/.test(text)) return null;
  if (text.length > 16) return null;
  try {
    const mid = BigInt(text);
    if (mid <= 0n) return null;
    if (mid <= BigInt(Number.MAX_SAFE_INTEGER)) return Number(text);
    return text;
  } catch {
    return null;
  }
}

async function submitWatchUser(event) {
  event.preventDefault();
  clearWatchMidError();
  if (!isLoggedIn()) {
    showToast("请先扫码登录", "info", "登录后才能管理监控用户");
    return;
  }
  const rawMid = String(watchAddMidInput?.value || "").trim();
  if (!rawMid) {
    showWatchMidError("请输入用户 MID");
    watchAddMidInput?.focus();
    return;
  }
  const mid = parseWatchMidInput(rawMid);
  if (mid === null) {
    showWatchMidError("请输入有效的 B 站用户 MID");
    watchAddMidInput?.focus();
    return;
  }
  setButtonLoading(watchAddBtn, true, { label: "添加中…" });
  try {
    const result = await fetchJSON("/api/watch-users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mid }),
    });
    if (watchAddForm) watchAddForm.reset();
    clearWatchMidError();
    await loadWatchUsers();
    highlightWatchUserChip(mid);
    const addedName = result?.user?.name || String(mid);
    if (result?.name_fallback) {
      showToast("已添加监控用户（昵称暂用 MID）", "info", addedName);
    } else {
      showToast("已添加监控用户", "success", addedName);
    }
  } catch (error) {
    const message = String(error.message || error);
    if (message.includes("已在监控列表")) {
      showWatchMidError(message);
      watchAddMidInput?.focus();
    } else {
      showWatchMidError(message);
    }
  } finally {
    setButtonLoading(watchAddBtn, false);
    updateWatchUserFormState();
  }
}

async function removeWatchUser(mid) {
  if (!isLoggedIn()) {
    showToast("请先扫码登录", "info", "登录后才能管理监控用户");
    return;
  }
  try {
    await fetchJSON(`/api/watch-users/${encodeURIComponent(mid)}`, { method: "DELETE" });
    await loadWatchUsers();
    showToast("已移出监控名单", "success");
  } catch (error) {
    showToast(String(error.message || error), "error");
  }
}

function bindWatchUsers() {
  watchAddForm?.addEventListener("submit", submitWatchUser);
  watchAddMidInput?.addEventListener("input", clearWatchMidError);
  watchUserGrid?.addEventListener("click", async (event) => {
    const cancelBtn = event.target.closest("[data-watch-cancel]");
    if (cancelBtn) {
      cancelBtn.closest(".watch-user-chip")?.classList.remove("is-confirming");
      return;
    }

    const confirmBtn = event.target.closest("[data-watch-confirm]");
    if (confirmBtn && !confirmBtn.disabled) {
      const mid = Number(confirmBtn.dataset.watchConfirm || 0);
      const chip = confirmBtn.closest(".watch-user-chip");
      if (!mid) return;
      setButtonLoading(confirmBtn, true);
      try {
        await removeWatchUser(mid);
        chip?.classList.remove("is-confirming");
      } finally {
        setButtonLoading(confirmBtn, false);
      }
      return;
    }

    const removeBtn = event.target.closest("[data-watch-remove]");
    if (!removeBtn || removeBtn.disabled) return;
    const chip = removeBtn.closest(".watch-user-chip");
    if (!chip) return;
    closeWatchUserConfirm(chip);
    chip.classList.add("is-confirming");
  });
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
            <div class="source-row-actions">
              <span class="source-status ${statusClass}">${statusText}</span>
              <button
                type="button"
                class="btn btn-secondary btn-compact btn-pill source-refresh-btn"
                data-action="refresh_source"
                data-source-id="${escapeHtml(source.id)}"
              >更新此源</button>
            </div>
          </div>
          <p class="source-row-meta">${source.link_count} 条链接 · ${escapeHtml(source.title || "暂无标题")}</p>
          <p class="source-row-time">最近检查：${escapeHtml(source.checked_at_text || "尚未更新")}</p>
          <div class="source-links">${links.join("") || '<span class="caption">暂无外链</span>'}</div>
        </div>
      </article>`;
    })
    .join("");
  bindActionButtons();
}

function buildActivityParticipateBtn(item) {
  if (item.can_participate) {
    return `<button class="btn btn-primary btn-compact btn-pill" data-action="participate" data-dynamic-id="${escapeHtml(item.dynamic_id)}">参与</button>`;
  }
  return `<span class="caption">—</span>`;
}

function buildActivityLastNote(item) {
  if (!item.last_participation) return "";
  return `<div class="last-result ${escapeHtml(item.last_participation.status || "")}">上次：${escapeHtml(formatLastParticipation(item.last_participation))}</div>`;
}

function buildActivityLink(item) {
  if (item.source_url) {
    return `<a class="activity-link" href="${escapeHtml(item.source_url)}" target="_blank" rel="noopener">打开动态</a>`;
  }
  return `<span class="caption">—</span>`;
}

function renderActivityTableRow(item) {
  const title = escapeHtml(item.activity_title || item.prize || "未知活动");
  return `
    <tr data-dynamic-id="${escapeHtml(item.dynamic_id || "")}">
      <td class="activity-cell">
        <div class="activity-title">${title}</div>
        ${buildActivityLastNote(item)}
      </td>
      <td class="link-cell">${buildActivityLink(item)}</td>
      <td class="chip-cell"><span class="type-chip">${escapeHtml(item.lottery_type)}</span></td>
      <td class="heat-cell"><span class="heat-pill${item.heat_missing ? " heat-pill-missing" : ""}">${formatHeat(item)}</span></td>
      <td class="chip-cell"><span class="${badgeClass(item.activity_status)}">${escapeHtml(item.activity_status)}</span></td>
      <td class="time-cell"><span class="time-pill">${escapeHtml(formatLotteryTime(item.lottery_time))}</span></td>
      <td class="chip-cell">${buildActivityParticipateBtn(item)}</td>
    </tr>`;
}

function renderActivityCard(item) {
  const title = escapeHtml(item.activity_title || item.prize || "未知活动");
  const ended = item.activity_status === "已结束" ? " is-ended" : "";
  return `
    <article class="activity-card${ended}" data-dynamic-id="${escapeHtml(item.dynamic_id || "")}">
      <div class="activity-card-head">
        <h3 class="activity-card-title">${title}</h3>
        <span class="${badgeClass(item.activity_status)}">${escapeHtml(item.activity_status)}</span>
      </div>
      ${buildActivityLastNote(item)}
      <div class="activity-card-meta">
        <span class="type-chip">${escapeHtml(item.lottery_type)}</span>
        <span class="heat-pill${item.heat_missing ? " heat-pill-missing" : ""}">${formatHeat(item)}</span>
        <span class="time-pill">${escapeHtml(formatLotteryTime(item.lottery_time))}</span>
      </div>
      <div class="activity-card-actions">
        ${buildActivityLink(item)}
        ${buildActivityParticipateBtn(item)}
      </div>
    </article>`;
}

function formatFilterSummary(payload) {
  const total = Number(payload.total) || 0;
  const page = Number(payload.page) || 1;
  const pages = Math.max(1, Number(payload.pages) || 1);
  const filters = [];
  const { q, type, status, drawWindow, sort, order } = state.filters;
  if (q) filters.push(`关键词「${escapeHtml(q)}」`);
  if (type) filters.push(escapeHtml(type));
  if (status) filters.push(escapeHtml(status));
  if (drawWindow === "soon") filters.push("即将开奖");
  if (sort === "heat") filters.push(order === "asc" ? "热度升序" : "热度降序");
  const filterText = filters.length ? `（${filters.join(" · ")}）` : "";
  if (total === 0) return `未找到匹配活动${filterText}`;
  return `共 <strong>${total}</strong> 条${filterText} · 第 ${page}/${pages} 页`;
}

function flashActivityRows(dynamicIds) {
  dynamicIds.forEach((dynamicId) => {
    if (!dynamicId) return;
    document.querySelectorAll(`[data-dynamic-id="${dynamicId}"]`).forEach((el) => {
      el.classList.add("row-flash");
      window.setTimeout(() => el.classList.remove("row-flash"), 1800);
    });
  });
}

function renderActivities(payload) {
  const items = payload.items || [];

  if (filterResultSummary) {
    filterResultSummary.innerHTML = formatFilterSummary(payload);
    filterResultSummary.hidden = false;
    pulseFilterSummary();
  }

  if (!items.length) {
    activitiesBody.innerHTML = `<tr class="empty-row"><td colspan="7">没有匹配的活动</td></tr>`;
    if (activitiesCards) {
      activitiesCards.innerHTML = `<p class="caption activity-cards-empty">没有匹配的活动</p>`;
    }
  } else {
    activitiesBody.innerHTML = items.map(renderActivityTableRow).join("");
    if (activitiesCards) activitiesCards.innerHTML = items.map(renderActivityCard).join("");
  }

  const page = Number(payload.page) || 1;
  const pages = Math.max(1, Number(payload.pages) || 1);
  const total = Number(payload.total) || 0;
  pagination.innerHTML = `
    <span class="caption pagination-summary">第 ${page} / ${pages} 页 · 本页 ${items.length} 条 · 共 ${total} 条</span>
    <div class="action-row pagination-actions">
      <button class="btn btn-secondary btn-compact btn-pill" id="page-prev" ${page <= 1 ? "disabled" : ""}>上一页</button>
      <button class="btn btn-secondary btn-compact btn-pill" id="page-next" ${page >= pages ? "disabled" : ""}>下一页</button>
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
  const preview = resolveTripleTargets(payload);
  if (preview) applyTripleTargets(preview);
}

function setProgressAria(percent, labelText) {
  if (!progressTrack) return;
  const rounded = Math.max(0, Math.min(100, Math.round(percent)));
  progressTrack.setAttribute("aria-valuenow", String(rounded));
  if (labelText) {
    progressTrack.setAttribute("aria-valuetext", labelText);
  }
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
    if (progressPercentSuffix) {
      progressPercentSuffix.textContent = "%";
      progressPercentSuffix.hidden = false;
    }
    if (progressRing) progressRing.style.strokeDashoffset = "97.4";
    state.smoothJobPercent = 0;
    state.activeJobKey = "";
    if (progressBanner) progressBanner.dataset.percent = "0";
    setProgressAria(0, "0%");
    renderParticipateSteps(job);
    return;
  }

  resetJobProgressTracking(job);
  const display = formatJobProgressDisplay(job);
  const percent = Math.max(state.smoothJobPercent, display.percent);
  state.smoothJobPercent = percent;
  const prev = Number(progressBanner.dataset.percent || "0");
  progressBanner.dataset.percent = String(percent);
  if (percent > prev) progressBanner.classList.add("progress-tick");
  else progressBanner.classList.remove("progress-tick");
  window.setTimeout(() => progressBanner.classList.remove("progress-tick"), 420);
  progressFill.style.width = `${percent}%`;
  if (progressFillGlow) progressFillGlow.style.width = `${percent}%`;
  const shine = document.getElementById("progress-fill-shine");
  if (shine) shine.style.left = `${Math.max(0, percent - 6)}%`;
  if (progressPercent) progressPercent.textContent = display.value;
  if (progressPercentSuffix) {
    progressPercentSuffix.textContent = display.suffix;
    progressPercentSuffix.hidden = !display.showPercentSuffix && !display.suffix;
  }
  if (progressRing) {
    const circumference = 97.4;
    progressRing.style.strokeDashoffset = String(circumference - (circumference * percent) / 100);
  }
  setProgressAria(percent, `${display.showPercentSuffix ? `${Math.round(percent)}%` : display.value}${display.suffix || ""}`.trim());
  if (progressChip) {
    const chipMap = {
      participate: "参与任务",
      participate_triple: "三连参与",
      refresh_all: "同步任务",
      refresh_source: "数据源更新",
      refresh_watch: "监控扫描",
      login: "登录任务",
    };
    progressChip.textContent = chipMap[job.action] || "任务进行中";
  }
  progressLabel.textContent = formatProgressTitle(job);
  if (progressDetail) {
    progressDetail.textContent = formatProgressDetail(job);
    progressDetail.hidden = job.action === "participate";
  }
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

function activateSection(sectionId) {
  const target = document.getElementById(`section-${sectionId}`);
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.section === sectionId);
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
    }
  });
  document.getElementById("sidebar")?.classList.remove("open");
  if (sectionId === "sources") {
    loadWatchUsers().catch(() => {});
  }
}

function switchSection(sectionId) {
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
  document.addEventListener("keydown", (event) => {
    trapQrcodeFocus(event);
    if (event.key === "Escape" && qrcodeModal && !qrcodeModal.hidden) {
      hideQrcodeModal(true);
    }
  });
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
  filterDrawWindowHint.textContent = "仅筛选你已参加、且 3 天内即将开奖的活动";
}

function buildActivityFilterQueryParams() {
  const params = new URLSearchParams();
  if (state.filters.draw) params.set("draw", state.filters.draw);
  if (state.filters.q) params.set("q", state.filters.q);
  if (state.filters.type) params.set("type", state.filters.type);
  if (state.filters.status) params.set("status", state.filters.status);
  if (state.filters.drawWindow) params.set("draw_window", state.filters.drawWindow);
  if (state.filters.sort) params.set("sort", state.filters.sort);
  if (state.filters.order) params.set("order", state.filters.order);
  return params;
}

function truncateText(text, maxLen = 28) {
  const value = String(text || "").trim();
  if (value.length <= maxLen) return value;
  return `${value.slice(0, maxLen - 1)}…`;
}

function renderTripleParticipateBar(data) {
  const descEl = document.getElementById("triple-participate-desc");
  const targetsEl = document.getElementById("triple-participate-targets");
  const btn = document.getElementById("triple-participate-btn");
  const labelEl = document.getElementById("triple-participate-btn-label");
  if (!btn || !targetsEl || !labelEl) return;

  const count = Number(data?.count) || 0;
  const items = data?.items || [];
  const jobRunning = document.body.classList.contains("job-running");

  if (!isSetupComplete()) {
    if (descEl) descEl.textContent = "完成登录与 LLM 配置后，可一键并行参与最多 3 个活动";
    targetsEl.innerHTML = "";
    btn.disabled = true;
    labelEl.textContent = "三连参与";
    return;
  }

  if (count <= 0) {
    if (descEl) descEl.textContent = "当前筛选列表下没有可参与的未参加活动";
    targetsEl.innerHTML = `<span class="triple-participate-empty">暂无可参与目标</span>`;
    btn.disabled = true;
    labelEl.textContent = "三连参与";
    return;
  }

  if (descEl) {
    const sortHint =
      state.filters.sort === "heat"
        ? state.filters.order === "asc"
          ? "（按热度升序）"
          : "（按热度降序）"
        : "";
    descEl.textContent =
      count === 1
        ? `将并行参与当前列表最前面的 1 个未参加活动${sortHint}`
        : `将并行参与当前列表最前面的 ${Math.min(count, 3)} 个未参加活动${sortHint}`;
  }
  targetsEl.innerHTML = items
    .map(
      (item, index) => `
      <span class="triple-target-chip" title="${escapeHtml(item.activity_title || item.dynamic_id)}">
        <span class="triple-target-chip-index">${index + 1}</span>
        <span class="triple-target-chip-title">${escapeHtml(truncateText(item.activity_title || item.dynamic_id))}</span>
        <span class="triple-target-chip-type">${escapeHtml(item.lottery_type || "")}</span>
      </span>`
    )
    .join("");
  btn.disabled = jobRunning;
  labelEl.textContent = count >= 3 ? "三连参与 (3)" : `三连参与 (${count})`;
}

function buildActivityFilterJobParams() {
  const params = {};
  if (state.filters.draw) params.draw = state.filters.draw;
  if (state.filters.q) params.q = state.filters.q;
  if (state.filters.type) params.lottery_type = state.filters.type;
  if (state.filters.status) params.status = state.filters.status;
  if (state.filters.drawWindow) params.draw_window = state.filters.drawWindow;
  if (state.filters.sort) params.sort = state.filters.sort;
  if (state.filters.order) params.order = state.filters.order;
  return params;
}

function getActiveFilterKey() {
  return JSON.stringify(state.filters);
}

function computeTripleTargetsFromItems(items) {
  const eligible = (items || []).filter(
    (item) => item?.can_participate && item.activity_status === "未参加"
  );
  const picked = eligible.slice(0, 3);
  return {
    count: picked.length,
    limit: 3,
    items: picked.map((item) => ({
      dynamic_id: String(item.dynamic_id || ""),
      activity_title: String(item.activity_title || item.prize || "未知活动"),
      lottery_type: String(item.lottery_type || ""),
      activity_status: String(item.activity_status || ""),
    })),
  };
}

function resolveTripleTargets(payload) {
  if (payload?.triple_targets && Array.isArray(payload.triple_targets.items)) {
    return payload.triple_targets;
  }
  if (state.page === 1) {
    return computeTripleTargetsFromItems(payload?.items || []);
  }
  return null;
}

function applyTripleTargets(data) {
  state.tripleTargets = data || { count: 0, limit: 3, items: [] };
  state.tripleFilterKey = getActiveFilterKey();
  renderTripleParticipateBar(state.tripleTargets);
}

async function loadTripleTargets() {
  try {
    const query = buildActivityFilterQueryParams().toString();
    const url = query ? `/api/activities/triple-targets?${query}` : "/api/activities/triple-targets";
    const data = await fetchJSON(url);
    applyTripleTargets(data);
  } catch {
    applyTripleTargets({ count: 0, limit: 3, items: [] });
  }
}

async function loadActivities() {
  const filterKey = getActiveFilterKey();
  const params = new URLSearchParams({
    page: String(state.page),
    page_size: String(state.pageSize),
  });
  buildActivityFilterQueryParams().forEach((value, key) => params.set(key, value));
  try {
    const payload = await fetchJSON(`/api/activities?${params.toString()}`);
    renderActivities(payload);
    const preview = resolveTripleTargets(payload);
    if (preview) {
      applyTripleTargets(preview);
    } else {
      await loadTripleTargets();
    }
    if (state.tripleFilterKey !== filterKey) {
      await loadTripleTargets();
    }
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
  if (action === "participate" || action === "participate_triple") {
    hideParticipationResult(true);
    state.smoothJobPercent = 0;
    state.activeJobKey = "";
  }
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

function collectFinishedDynamicIds(job) {
  if (job.action === "participate_triple") {
    return (job.result?.items || []).map((item) => item?.dynamic_id).filter(Boolean);
  }
  if (job.action === "participate" && job.result?.dynamic_id) {
    return [job.result.dynamic_id];
  }
  return [];
}

async function handleJobCompletion(job) {
  dismissRunningToasts();

  const isParticipation = job.action === "participate" || job.action === "participate_triple";
  if (job.action === "login" && job.state === "success" && !state.qrcodeDismissed) {
    renderQrcodeLoginState({
      ...job,
      result: { ...(job.result || {}), login_phase: "success" },
      message: "登录成功，账号已就绪",
    });
    await new Promise((resolve) => window.setTimeout(resolve, 450));
  }

  if (isParticipation && (job.state === "success" || job.state === "error")) {
    if (job.result?.skipped) {
      if (!job.result?.from_auto) {
        showToast(sanitizeUserText(job.message) || "当前没有可参与活动，已跳过", "info");
      }
    } else {
      showParticipationResult(job);
    }
  } else if (job.state === "success") {
    if (SYNC_TOAST_ACTIONS.has(job.action)) {
      const detail = formatToastDetail(job);
      showToast(sanitizeUserText(job.message) || "任务完成", "success", detail);
    }
  } else if (job.state === "error") {
    if (job.action === "login" && !state.qrcodeDismissed) {
      renderQrcodeLoginState({
        ...job,
        result: { ...(job.result || {}), login_phase: "error" },
        message: sanitizeUserText(job.message) || "登录失败，请重试",
      });
    } else {
      showToast(sanitizeUserText(job.message) || "任务失败", "error", formatToastDetail(job));
    }
  }

  const finishedDynamicIds = collectFinishedDynamicIds(job);
  try {
    await loadSummary();
    await syncProjectState();
    await loadActivities();
    if (job.action === "refresh_watch") {
      await loadWatchUsers();
    }
  } catch (error) {
    showToast(String(error.message || error), "error");
  }
  clearActionButtonLoading();
  if (job.action === "participate_triple") {
    renderTripleParticipateBar(state.tripleTargets);
  }
  flashActivityRows(finishedDynamicIds);
  if (job.action === "login" && job.state === "success") hideQrcodeModal(false);
}

function bindActionButtons() {
  document.querySelectorAll("[data-action]").forEach((button) => {
    if (button.dataset.bound === "true") return;
    button.dataset.bound = "true";
    button.addEventListener("click", async () => {
      const action = button.dataset.action;
      const params = {};
      if (button.dataset.dynamicId) params.dynamic_id = button.dataset.dynamicId;
      if (button.dataset.sourceId) params.source_id = button.dataset.sourceId;
      if (action === "participate_triple") {
        Object.assign(params, buildActivityFilterJobParams());
      }
      if (action === "participate") {
        setButtonLoading(button, true, { label: "参与中…" });
      }
      if (action === "participate_triple") {
        setButtonLoading(button, true, { label: "参与中" });
      }
      if (action === "refresh_source") {
        setButtonLoading(button, true, { label: "更新中…" });
      }
      try {
        await startJob(action, params);
      } catch (error) {
        showToast(String(error.message || error), "error");
        setButtonLoading(button, false);
        if (action === "participate_triple") {
          renderTripleParticipateBar(state.tripleTargets);
        }
      }
    });
  });
}

function resolveJobPollIntervalMs(action) {
  if (action === "login") return 500;
  if (action === "participate" || action === "participate_triple") return 400;
  return 1000;
}

function stopJobPolling() {
  if (state.polling) {
    window.clearTimeout(state.polling);
    state.polling = null;
  }
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
        state.polling = window.setTimeout(poll, resolveJobPollIntervalMs(job.action));
        return;
      }
      if (job.state === "idle" && job.action === "login") {
        stopJobPolling();
        setButtonsDisabled(false);
        hideQrcodeModal(false);
        updateJobUI(job);
        return;
      }
      stopJobPolling();
      await handleJobCompletion(job);
    } catch (error) {
      console.error(error);
      state.polling = window.setTimeout(poll, 1500);
    }
  };
  poll();
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
    if (!merged?.at_alert?.increased) {
      showToast("状态已同步", "success");
    }
  } catch (error) {
    showToast(String(error.message || error), "error");
  } finally {
    setButtonLoading(sidebarRefreshBtn, false);
  }
});

sidebarLogoutBtn?.addEventListener("click", async () => {
  const confirmed = await requestLogoutConfirm();
  if (!confirmed) return;
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
  setLogDockOpen(false);
  setAutoDockOpen(false);
  bindNavigation();
  bindAutoDock();
  bindFilterPills();
  bindParticipateSettings();
  bindLlmApiKeyToggle();
  bindWatchUsers();
  bindActionButtons();
  await syncProjectState();
  try {
    const job = await loadSummary();
    fetchAutoStatus().catch(() => {});
    loadWatchUsers().catch(() => {});
    await loadActivities();
    if (job?.state === "running") startPolling();
  } catch (error) {
    showToast(sanitizeUserText(error.message || error) || "数据加载失败", "error");
  }
}

function initSystemPreferences() {
  applySidebarCollapsed(localStorage.getItem("binggo-sidebar-collapsed") === "1", { animate: false });
  applyTheme(localStorage.getItem("binggo-theme") === "dark" ? "dark" : "light");
  document.getElementById("sidebar-collapse")?.addEventListener("click", () => {
    const collapsed = !document.querySelector(".app-shell")?.classList.contains("sidebar-collapsed");
    applySidebarCollapsed(collapsed);
  });
  document.getElementById("theme-toggle")?.addEventListener("click", () => {
    const isDark = document.documentElement.dataset.theme === "dark";
    applyTheme(isDark ? "light" : "dark");
  });
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

const SIDEBAR_ANIM_MS = 400;

function applySidebarCollapsed(collapsed, { animate = true } = {}) {
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

function applyTheme(theme) {
  const next = theme === "dark" ? "dark" : "light";
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
