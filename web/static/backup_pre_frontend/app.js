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
  autoLogs: [],
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
  lastJobAttempt: null,
  onboardingCelebrating: false,
  statValues: {},
  currentJob: null,
  eventSource: null,
  sseHealthy: false,
  sseLastActive: 0,
  sseWatchdog: null,
  sseReconnectTimer: null,
  lastFinishedJobKey: "",
};

const SSE_WATCHDOG_MS = 45000;
const SSE_RECONNECT_MS = 3000;

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
const appConfirmModal = document.getElementById("app-confirm-modal");
const appConfirmBackdrop = document.getElementById("app-confirm-backdrop");
const appConfirmEyebrow = document.getElementById("app-confirm-eyebrow");
const appConfirmTitle = document.getElementById("app-confirm-title");
const appConfirmDesc = document.getElementById("app-confirm-desc");
const appConfirmBullets = document.getElementById("app-confirm-bullets");
const appConfirmCancel = document.getElementById("app-confirm-cancel");
const appConfirmYes = document.getElementById("app-confirm-yes");
const appConfirmSecondary = document.getElementById("app-confirm-secondary");
const onboardingPanel = document.getElementById("onboarding-panel");
const onboardingStepsEl = document.getElementById("onboarding-steps");
const onboardingProgressFill = document.getElementById("onboarding-progress-fill");
const onboardingProgressLabel = document.getElementById("onboarding-progress-label");
const onboardingFootNote = document.getElementById("onboarding-foot-note");
const onboardingPrimaryBtn = document.getElementById("onboarding-primary");
const onboardingSkipBtn = document.getElementById("onboarding-skip");
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
const jobResultHint = document.getElementById("job-result-hint");
const jobResultActions = document.getElementById("job-result-actions");
const jobResultBody = document.getElementById("job-result-body");
const jobResultProgress = document.getElementById("job-result-progress");
const jobResultClose = document.getElementById("job-result-close");
const toastStack = document.getElementById("toast-stack");

const JOB_RESULT_AUTO_DISMISS_MS = 3000;
const JOB_RESULT_EXIT_MS = 340;
const JOB_RESULT_HOVER_DISMISS_MS = 2200;
const INLINE_FEEDBACK_MS = 5000;
const ONBOARDING_STORAGE_KEY = "binggo-onboarding-v1";
const ONBOARDING_STEPS = [
  {
    id: "login",
    title: "扫码登录",
    desc: "使用哔哩哔哩 App 扫码，登录后才能参与抽奖与保存配置。",
    cta: "去登录",
  },
  {
    id: "llm_save",
    title: "保存 LLM 配置",
    desc: "填写 API Key 与模型名称并保存。转发抽奖解析依赖 LLM，为项目启动的必要条件。",
    cta: "去配置",
  },
  {
    id: "llm_test",
    title: "测试 LLM 连接",
    desc: "保存后点击「测试连接」，通过后才能使用参与、刷新等功能。",
    cta: "去测试",
  },
  {
    id: "try",
    title: "去活动页试一次",
    desc: "进入活动列表，尝试参与单个活动或使用「三连参与」。",
    cta: "去活动页",
  },
];
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
const autoDockScheduler = document.getElementById("auto-dock-scheduler");
const autoDockPhase = document.getElementById("auto-dock-phase");
const autoDockHint = document.getElementById("auto-dock-hint");
const autoDockPipeline = document.getElementById("auto-dock-pipeline");
const autoDockToggleMeta = document.getElementById("auto-dock-toggle-meta");
const autoDockFatal = document.getElementById("auto-dock-fatal");
const autoDockFatalText = document.getElementById("auto-dock-fatal-text");
const autoDockStartBtn = document.getElementById("auto-dock-start");
const autoDockStopBtn = document.getElementById("auto-dock-stop");

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
  document.querySelectorAll(".source-row.is-updating").forEach((row) => {
    row.classList.remove("is-updating");
  });
}

function setSourceRowUpdating(sourceId, updating) {
  if (!sourceId) return;
  const row = document.querySelector(`.source-row[data-source-id="${CSS.escape(String(sourceId))}"]`);
  if (!row) return;
  row.classList.toggle("is-updating", Boolean(updating));
}

function flashSourceRow(sourceId) {
  if (!sourceId || prefersReducedMotion()) return;
  const row = document.querySelector(`.source-row[data-source-id="${CSS.escape(String(sourceId))}"]`);
  if (!row) return;
  row.classList.remove("is-flash");
  void row.offsetWidth;
  row.classList.add("is-flash");
  window.setTimeout(() => row.classList.remove("is-flash"), 1100);
}

function pulseWatchSyncCard() {
  const card = document.querySelector(".watch-sync-card");
  if (!card || prefersReducedMotion()) return;
  card.classList.remove("is-sync-pulse");
  void card.offsetWidth;
  card.classList.add("is-sync-pulse");
  document.querySelectorAll(".watch-metric-value").forEach((el) => {
    el.classList.remove("is-value-pop");
    void el.offsetWidth;
    el.classList.add("is-value-pop");
  });
  window.setTimeout(() => {
    card.classList.remove("is-sync-pulse");
    document.querySelectorAll(".watch-metric-value").forEach((el) => el.classList.remove("is-value-pop"));
  }, 900);
}

function playSourcesEnter() {
  const stack = document.querySelector("#section-sources .sources-stack");
  if (!stack || prefersReducedMotion()) return;
  stack.classList.remove("is-sources-entering");
  void stack.offsetWidth;
  stack.classList.add("is-sources-entering");
}

function playActivitiesEnter() {
  const panel = document.querySelector("#section-activities .activities-panel");
  if (!panel || prefersReducedMotion()) return;
  panel.classList.remove("is-activities-entering");
  void panel.offsetWidth;
  panel.classList.add("is-activities-entering");
}

function pulseFilterSummary() {
  if (!filterResultSummary || prefersReducedMotion()) return;
  filterResultSummary.classList.remove("is-updated");
  void filterResultSummary.offsetWidth;
  filterResultSummary.classList.add("is-updated");
}

function flashFilterPill(button) {
  if (!button || prefersReducedMotion()) return;
  button.classList.remove("is-just-selected");
  void button.offsetWidth;
  button.classList.add("is-just-selected");
  window.setTimeout(() => button.classList.remove("is-just-selected"), 520);
}

function playActivityListEnter() {
  if (prefersReducedMotion()) return;
  const rows = document.querySelectorAll("#activities-body tr[data-dynamic-id], #activities-cards .activity-card");
  rows.forEach((el, index) => {
    el.classList.remove("is-row-entering");
    el.style.setProperty("--row-delay", `${Math.min(index, 12) * 28}ms`);
    void el.offsetWidth;
    el.classList.add("is-row-entering");
  });
}

function lotteryTypeTone(type) {
  const text = String(type || "");
  if (text.includes("互动")) return "interact";
  if (text.includes("转发")) return "repost";
  if (text.includes("预约")) return "reserve";
  return "default";
}

function isLotterySoon(value) {
  const text = String(value || "").trim();
  const match = text.match(/^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})$/);
  if (!match) return false;
  const [, y, m, d, hh, mm] = match.map(Number);
  const target = new Date(y, m - 1, d, hh, mm).getTime();
  if (Number.isNaN(target)) return false;
  const now = Date.now();
  const delta = target - now;
  return delta >= 0 && delta <= 3 * 24 * 60 * 60 * 1000;
}

function activityStatusTone(status) {
  if (status === "已参加") return "joined";
  if (status === "已结束") return "ended";
  return "pending";
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
      <span class="setup-pill ${loggedIn ? "ok" : "warn"}"><span class="setup-pill-dot" aria-hidden="true"></span>账号${loggedIn ? "已登录" : "未登录"}</span>
      <span class="setup-pill ${llmOk ? "ok" : "warn"}"><span class="setup-pill-dot" aria-hidden="true"></span>LLM${llmOk ? "已配置" : "未配置"}</span>
      <span class="setup-pill ${llmTested ? "ok" : "warn"}"><span class="setup-pill-dot" aria-hidden="true"></span>连接${llmTested ? "已通过" : "未测试"}</span>
    </div>`;
}

function getAccountHeroTone(account) {
  if (!account?.logged_in) {
    return account?.network_error && account?.cookie_saved ? "offline" : "warn";
  }
  if (isSetupComplete()) return "ready";
  return "warn";
}

function renderAccountAvatar(account, { large = false } = {}) {
  const sizeClass = large ? " account-avatar-lg" : "";
  if (account?.face) {
    return `<img class="account-avatar${sizeClass}" src="${escapeHtml(account.face)}" alt="头像" referrerpolicy="no-referrer" crossorigin="anonymous" />`;
  }
  return `<div class="account-avatar account-avatar-fallback${sizeClass}"></div>`;
}

function renderAccountAvatarWrap(account, { large = false } = {}) {
  const tone = getAccountHeroTone(account);
  const sizeClass = large ? " is-lg" : " is-sm";
  return `
    <div class="account-avatar-wrap${sizeClass} is-${tone}" data-tone="${tone}">
      ${renderAccountAvatar(account, { large })}
      <span class="account-status-dot" aria-hidden="true"></span>
    </div>`;
}

function flashButtonSuccess(button, label = "已保存") {
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

function markSaveDirty(button) {
  button?.classList.add("is-dirty");
}

function clearSaveDirty(button) {
  button?.classList.remove("is-dirty");
}

function animateStatValue(el, from, to) {
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
  const tick = (now) => {
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

function renderAccountStatusLabel(account) {
  if (isSetupComplete()) return "已就绪";
  if (account.expired) return "需重新扫码登录";
  if (!isLlmConfigured()) return "请完成 LLM 配置";
  if (!isLlmTested()) return "请完成 LLM 连接测试";
  return "请完成登录与配置";
}

function isOnboardingDismissed() {
  try {
    return localStorage.getItem(ONBOARDING_STORAGE_KEY) === "done";
  } catch {
    return false;
  }
}

function dismissOnboarding() {
  try {
    localStorage.setItem(ONBOARDING_STORAGE_KEY, "done");
  } catch {
    /* ignore */
  }
  state.onboardingCelebrating = false;
  renderOnboardingPanel();
}

function getOnboardingCompletion() {
  return {
    login: isLoggedIn(),
    llm_save: isLlmConfigured(),
    llm_test: isLlmTested(),
    try: false,
  };
}

function countOnboardingDone(completion) {
  let done = 0;
  if (completion.login) done += 1;
  if (completion.llm_save) done += 1;
  if (completion.llm_test) done += 1;
  return done;
}

function getOnboardingCurrentIndex(completion) {
  if (!completion.login) return 0;
  if (!completion.llm_save) return 1;
  if (!completion.llm_test) return 2;
  return 3;
}

function scrollToLlmSettings({ focusTest = false } = {}) {
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

function runOnboardingStepAction(stepId) {
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

function renderOnboardingPanel() {
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

function bindOnboardingPanel() {
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

function closeAppConfirm() {
  if (!appConfirmModal) return;
  appConfirmModal.hidden = true;
  document.body.classList.remove("modal-open");
}

function openAppConfirm({
  eyebrow = "",
  title = "",
  desc = "",
  bullets = [],
  confirmLabel = "确认",
  cancelLabel = "取消",
  secondaryLabel = "",
  danger = false,
  onSecondary = null,
} = {}) {
  return new Promise((resolve) => {
    if (!appConfirmModal || !appConfirmCancel || !appConfirmYes) {
      resolve(window.confirm(title || "确认继续？"));
      return;
    }

    const cleanup = () => {
      closeAppConfirm();
      appConfirmCancel.removeEventListener("click", onCancel);
      appConfirmYes.removeEventListener("click", onConfirm);
      appConfirmBackdrop?.removeEventListener("click", onCancel);
      appConfirmSecondary?.removeEventListener("click", onSecondaryClick);
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

    const onSecondaryClick = () => {
      cleanup();
      try {
        onSecondary?.();
      } catch {
        /* ignore */
      }
      resolve(false);
    };

    const onKeyDown = (event) => {
      if (event.key === "Escape") onCancel();
    };

    if (appConfirmEyebrow) appConfirmEyebrow.textContent = eyebrow;
    if (appConfirmTitle) appConfirmTitle.textContent = title;
    if (appConfirmDesc) {
      if (desc) {
        appConfirmDesc.hidden = false;
        appConfirmDesc.textContent = desc;
      } else {
        appConfirmDesc.hidden = true;
        appConfirmDesc.textContent = "";
      }
    }
    if (appConfirmBullets) {
      if (bullets.length) {
        appConfirmBullets.hidden = false;
        appConfirmBullets.innerHTML = bullets.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
      } else {
        appConfirmBullets.hidden = true;
        appConfirmBullets.innerHTML = "";
      }
    }
    appConfirmCancel.textContent = cancelLabel;
    appConfirmYes.textContent = confirmLabel;
    appConfirmYes.classList.toggle("btn-danger", Boolean(danger));
    if (appConfirmSecondary) {
      const showSecondary = Boolean(secondaryLabel);
      appConfirmSecondary.toggleAttribute("hidden", !showSecondary);
      appConfirmSecondary.textContent = showSecondary ? secondaryLabel : "";
    }

    appConfirmModal.hidden = false;
    document.body.classList.add("modal-open");
    appConfirmCancel.addEventListener("click", onCancel);
    appConfirmYes.addEventListener("click", onConfirm);
    appConfirmBackdrop?.addEventListener("click", onCancel);
    if (secondaryLabel && appConfirmSecondary) {
      appConfirmSecondary.addEventListener("click", onSecondaryClick);
    }
    document.addEventListener("keydown", onKeyDown);
    appConfirmCancel.focus();
  });
}

function confirmRefreshAll() {
  return openAppConfirm({
    eyebrow: "数据源",
    title: "确认一键更新全部数据源？",
    bullets: [
      "将并行检查全部 6 个 UP 合集，请求量较大，容易触发 B 站风控",
      "日常更推荐在「数据源」页对单个 UP 点「更新此源」",
      "适合长时间未打开、想一次性扫完全部源时使用",
    ],
    confirmLabel: "仍要一键更新",
    cancelLabel: "取消",
    secondaryLabel: "去数据源页",
    onSecondary: () => switchSection("sources"),
  });
}

function buildFailureContext(message, action, log = "") {
  const parts = [message, log].map((item) => sanitizeUserText(String(item || ""))).filter(Boolean);
  const text = parts.join("\n");
  return { text, lowered: text.toLowerCase(), action: String(action || "") };
}

function classifyFailureText(message, action, log = "") {
  const { text, lowered, action: actionName } = buildFailureContext(message, action, log);
  const displayMessage = sanitizeUserText(message) || sanitizeUserText(log) || "操作失败，请稍后重试";

  if (/无可参与|没有可参与|已跳过/.test(text)) {
    return {
      kind: "empty",
      severity: "info",
      title: "提示",
      message: displayMessage,
      hint: "",
      actions: [],
      retryable: false,
    };
  }
  if (/已取消扫码|取消扫码登录|任务已取消/.test(text)) {
    return {
      kind: "cancelled",
      severity: "info",
      title: "提示",
      message: displayMessage,
      hint: "",
      actions: [],
      retryable: false,
    };
  }
  if (actionName === "login" || /二维码|扫码登录|sessdata|确认超时|登录未完成/.test(lowered)) {
    return {
      kind: "login",
      severity: "error",
      title: "登录未完成",
      message: displayMessage,
      hint: "请重新发起扫码登录，并在手机上确认。",
      actions: [{ id: "login", label: "重新扫码" }],
      retryable: true,
    };
  }
  if (/cookie|未登录|请先扫码|登录失效|重新扫码登录|未检测到有效登录/.test(lowered)) {
    return {
      kind: "auth",
      severity: "error",
      title: "需要登录",
      message: displayMessage,
      hint: "本地登录状态已失效，请重新扫码。",
      actions: [{ id: "login", label: "去登录" }],
      retryable: true,
    };
  }
  if (/llm|未配置|连接测试|api key|模型名称|无法连接 llm/.test(lowered)) {
    return {
      kind: "llm",
      severity: "error",
      title: "LLM 未就绪",
      message: displayMessage,
      hint: "在概览页填写 API Key 与模型名称，保存并通过连接测试。",
      actions: [{ id: "llm", label: "去配置 LLM" }],
      retryable: true,
    };
  }
  if (/频繁|限流|412|509|风控|-509/.test(lowered)) {
    const actions = [{ id: "retry", label: "稍后重试" }];
    if (actionName === "refresh_all" || actionName === "refresh_source") {
      actions.push({ id: "sources", label: "去数据源页" });
    }
    return {
      kind: "rate",
      severity: "error",
      title: "请求过于频繁",
      message: displayMessage,
      hint: "建议等待几分钟后重试，或改用单个数据源更新。",
      actions,
      retryable: true,
    };
  }
  if (/timeout|ssl|handshake|无法连接|网络|dns|代理|请求超时/.test(lowered)) {
    return {
      kind: "network",
      severity: "error",
      title: "网络异常",
      message: displayMessage,
      hint: "请检查本机网络、代理或 DNS，然后重试。",
      actions: [{ id: "retry", label: "重试" }],
      retryable: true,
    };
  }
  if (/已有任务|正在运行|仍在运行|撞车/.test(text)) {
    return {
      kind: "busy",
      severity: "error",
      title: "任务冲突",
      message: displayMessage,
      hint: "请等待当前任务结束后再试。",
      actions: [],
      retryable: false,
    };
  }
  if (/未找到活动|活动 id 无效|缺少 dynamic/.test(lowered)) {
    return {
      kind: "not_found",
      severity: "error",
      title: "活动不可用",
      message: displayMessage,
      hint: "列表可能已过期，刷新活动后再试。",
      actions: [{ id: "refresh_activities", label: "刷新列表" }],
      retryable: false,
    };
  }
  return {
    kind: "generic",
    severity: "error",
    title: "执行失败",
    message: displayMessage,
    hint: "若持续失败，可查看右下角任务日志了解详情。",
    actions: [{ id: "retry", label: "重试" }],
    retryable: true,
  };
}

function classifyJobFailure(job) {
  return classifyFailureText(job?.message, job?.action, job?.log);
}

async function executeFailureAction(actionId) {
  switch (actionId) {
    case "login":
      sidebarLoginBtn?.click();
      break;
    case "llm":
      scrollToLlmSettings({ focusTest: !isLlmConfigured() });
      break;
    case "retry":
      if (state.lastJobAttempt?.action) {
        await startJob(state.lastJobAttempt.action, { ...(state.lastJobAttempt.params || {}) });
      }
      break;
    case "sources":
      switchSection("sources");
      break;
    case "refresh_activities":
      await loadActivities();
      break;
    default:
      break;
  }
}

function renderFailureActions(container, failure, job) {
  if (!container) return;
  const actions = failure?.actions || [];
  if (!actions.length) {
    container.hidden = true;
    container.innerHTML = "";
    return;
  }
  container.hidden = false;
  container.innerHTML = actions
    .map(
      (action) =>
        `<button type="button" class="btn btn-secondary btn-compact btn-pill" data-failure-action="${escapeHtml(action.id)}">${escapeHtml(action.label)}</button>`
    )
    .join("");
  container.querySelectorAll("[data-failure-action]").forEach((button) => {
    button.addEventListener("click", () => {
      if (job?.action) {
        state.lastJobAttempt = {
          action: job.action,
          params: { ...(state.lastJobAttempt?.params || {}) },
        };
      }
      executeFailureAction(button.dataset.failureAction);
    });
  });
}

function showFailureToast(failure, job) {
  if (!failure || failure.severity === "info") {
    showToast(failure?.message || "提示", "info", failure?.hint || "");
    return;
  }
  if (job?.action && failure.retryable !== false) {
    state.lastJobAttempt = {
      action: job.action,
      params: { ...(state.lastJobAttempt?.params || {}) },
    };
  }
  const actions = (failure.actions || []).map((action) => ({
    label: action.label,
    onClick: () => executeFailureAction(action.id),
  }));
  showToast(failure.message, "error", failure.hint || formatToastDetail(job), actions);
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
      let code = "";
      let detail = null;
      try {
        const payload = JSON.parse(text);
        const errObj = payload?.error;
        if (errObj && typeof errObj === "object") {
          if (errObj.message) message = String(errObj.message);
          code = String(errObj.code || "");
          detail = errObj.detail ?? null;
        } else if (typeof payload?.detail === "string") {
          message = payload.detail;
        } else if (Array.isArray(payload?.detail)) {
          message = "请求参数无效";
          detail = payload.detail;
        }
      } catch {
        // 非 JSON 响应，保留原始文本
      }
      const error = new Error(message);
      error.code = code;
      error.httpStatus = response.status;
      error.detail = detail;
      throw error;
    }
    return response.json();
  } catch (error) {
    if (error.name === "AbortError") throw new Error("请求超时，请稍后重试");
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}

function showToast(message, type = "info", detail = "", actions = []) {
  if (!toastStack || !message) return;
  const meta = TOAST_META[type] || TOAST_META.info;
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  const actionHtml = actions.length
    ? `<div class="toast-actions">${actions
        .map(
          (action, index) =>
            `<button type="button" class="btn btn-secondary btn-compact btn-pill toast-action-btn" data-toast-action="${index}">${escapeHtml(action.label)}</button>`
        )
        .join("")}</div>`
    : "";
  toast.innerHTML = `
    <div class="toast-icon" aria-hidden="true">${meta.icon}</div>
    <div class="toast-body">
      <p class="toast-title">${escapeHtml(meta.title)}</p>
      <p class="toast-message">${escapeHtml(message)}</p>
      ${detail ? `<p class="toast-detail">${escapeHtml(detail)}</p>` : ""}
      ${actionHtml}
    </div>
    <button type="button" class="toast-close" aria-label="关闭">×</button>
    <div class="toast-progress" aria-hidden="true"></div>`;
  const duration = type === "error" ? 8000 : type === "running" ? 2400 : 4200;
  const progress = toast.querySelector(".toast-progress");
  progress.style.animationDuration = `${duration}ms`;
  toast.querySelector(".toast-close")?.addEventListener("click", () => toast.remove());
  toast.querySelectorAll("[data-toast-action]").forEach((button) => {
    button.addEventListener("click", () => {
      const action = actions[Number(button.dataset.toastAction)];
      toast.remove();
      action?.onClick?.();
    });
  });
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
  if (!prefersReducedMotion()) {
    element.classList.remove("is-feedback-pop");
    void element.offsetWidth;
    element.classList.add("is-feedback-pop");
  }

  if (autoHide && type !== "info") {
    const timer = window.setTimeout(() => setInlineFeedback(element, "", "info"), INLINE_FEEDBACK_MS);
    inlineFeedbackTimers.set(element, timer);
  }
}

function playOverviewEnter() {
  const stack = document.querySelector("#section-overview .overview-stack");
  if (!stack || prefersReducedMotion()) return;
  stack.classList.remove("is-overview-entering");
  void stack.offsetWidth;
  stack.classList.add("is-overview-entering");
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

function syncLogDockTone(job) {
  if (!logDock) return;
  const jobState = job?.state || "idle";
  let tone = "idle";
  if (jobState === "running") tone = "running";
  else if (jobState === "success") tone = "success";
  else if (jobState === "error") tone = "error";

  logDock.dataset.tone = tone;
  logDock.classList.toggle("is-idle", tone === "idle");
  logDock.classList.toggle("is-running", tone === "running");
  logDock.classList.toggle("is-success", tone === "success");
  logDock.classList.toggle("is-error", tone === "error");

  const statusEl = document.getElementById("log-dock-status");
  if (statusEl) {
    const labels = { idle: "空闲", running: "运行中", success: "已完成", error: "失败" };
    statusEl.textContent = labels[tone] || "空闲";
    statusEl.className = `log-dock-status is-${tone}`;
  }
  if (logDockBadge) {
    logDockBadge.hidden = tone !== "running";
    logDockBadge.textContent = "运行中";
  }
}

function scrollJobLogToBottom({ showHint = false } = {}) {
  const box = document.getElementById("job-log");
  const hint = document.getElementById("log-dock-pin-hint");
  const body = document.getElementById("log-dock-body");
  if (!box) return;
  box.scrollTop = box.scrollHeight;
  body?.classList.toggle("is-pinned", Boolean(showHint));
  if (hint) {
    hint.hidden = !showHint;
    if (showHint && !prefersReducedMotion()) {
      hint.classList.remove("is-hint-pop");
      void hint.offsetWidth;
      hint.classList.add("is-hint-pop");
    }
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
  if (open) {
    if (!prefersReducedMotion()) {
      logDockPanel.classList.remove("is-entering");
      void logDockPanel.offsetWidth;
      logDockPanel.classList.add("is-entering");
    }
    scrollJobLogToBottom({ showHint: logDock?.classList.contains("is-running") });
  } else {
    logDockPanel.classList.remove("is-entering");
    document.getElementById("log-dock-body")?.classList.remove("is-pinned");
    const hint = document.getElementById("log-dock-pin-hint");
    if (hint) hint.hidden = true;
  }
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
    if (!prefersReducedMotion()) {
      autoDockPanel.classList.remove("is-entering");
      void autoDockPanel.offsetWidth;
      autoDockPanel.classList.add("is-entering");
    }
    fetchAutoStatus().catch(() => {});
    ensureAutoPolling();
    ensureAutoCountdown();
    tickAutoCountdown();
  } else {
    autoDockPanel.classList.remove("is-entering");
    if (!(state.autoScheduler && state.autoScheduler.state === "running")) {
      stopAutoPolling();
    }
  }
}

function getAutoCountdownSeconds(targetUnix) {
  if (!targetUnix) return null;
  const nowSec = Math.floor((Date.now() + state.autoServerSkewMs) / 1000);
  return Math.max(0, Number(targetUnix) - nowSec);
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

function resolveAutoSchedulerText(status) {
  const schedulerState = String(status?.state || "idle");
  if (schedulerState === "fatal") {
    return sanitizeUserText(status.fatal_error || status.message || "已停机");
  }
  if (schedulerState !== "running") {
    return sanitizeUserText(status.state_label || status.message || "尚未启动");
  }
  const phase = sanitizeUserText(status.current_phase || "");
  if (phase && phase !== "—") return phase;
  return sanitizeUserText(status.message || "调度运行中");
}

function resolveAutoJobText(status) {
  const jobProbe = status?.job_probe || {};
  const jobState = String(jobProbe.job_state || "idle");
  const jobLabel = sanitizeUserText(jobProbe.job_label || jobProbe.job_action || "");
  if (jobState === "running") {
    return jobLabel ? `运行中 · ${jobLabel}` : "运行中";
  }
  if (jobState === "idle") return "空闲";
  if (jobState === "success") return jobLabel ? `刚完成 · ${jobLabel}` : "刚完成";
  if (jobState === "error") return jobLabel ? `出错 · ${jobLabel}` : "出错";
  return jobLabel || jobState || "—";
}

function resolveAutoJobTone(status) {
  const jobState = String(status?.job_probe?.job_state || "idle");
  if (jobState === "running") return "running";
  if (jobState === "error") return "error";
  if (jobState === "success") return "success";
  return "idle";
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

function updateAutoCollapsedMeta(status) {
  if (!autoDockToggleMeta) return;
  const schedulerState = String(status?.state || "idle");
  if (schedulerState === "running") {
    const countdown = formatAutoCountdown(status?.next_slot?.at_unix);
    autoDockToggleMeta.hidden = false;
    autoDockToggleMeta.textContent = countdown === "—" ? "…" : countdown;
    return;
  }
  // fatal / idle：角标或默认文案已够，折叠态不再重复「已停机」
  autoDockToggleMeta.hidden = true;
  autoDockToggleMeta.textContent = "";
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
    // 头部只保留短状态，长进度细节交给「调度 / 抽奖任务」行
    autoDockStatus.textContent =
      schedulerState === "running"
        ? sanitizeUserText(status.state_label || "调度器运行中")
        : message || stateLabel;
  }
  if (autoDockPhase) {
    autoDockPhase.textContent = phase;
    autoDockPhase.classList.toggle("is-live", schedulerState === "running");
  }
  if (autoDockHint) {
    autoDockHint.textContent = hint;
  }
  const hero = document.querySelector(".auto-dock-hero");
  const pipelineBlock = document.querySelector(".auto-dock-pipeline-block");
  const countdownSec = getAutoCountdownSeconds(status.next_slot?.at_unix);
  const urgent = schedulerState === "running" && countdownSec !== null && countdownSec > 0 && countdownSec < 60;
  if (hero) {
    hero.classList.toggle("is-live", schedulerState === "running");
    hero.classList.toggle("is-urgent", urgent);
  }
  if (pipelineBlock) {
    pipelineBlock.classList.toggle("is-active", Boolean(status.refresh_pipeline?.active));
  }
  if (autoDockScheduler) {
    autoDockScheduler.textContent = resolveAutoSchedulerText(status);
    autoDockScheduler.dataset.tone = schedulerState === "fatal" ? "error" : schedulerState === "running" ? "running" : "idle";
  }
  if (autoDockJob) {
    autoDockJob.textContent = resolveAutoJobText(status);
    autoDockJob.dataset.tone = resolveAutoJobTone(status);
  }
  tickAutoCountdown();
  renderAutoPipeline(status.refresh_pipeline);
  updateAutoCollapsedMeta(status);

  const running = schedulerState === "running";
  const fatal = schedulerState === "fatal";

  autoDock?.classList.toggle("fatal", fatal);
  autoDock?.classList.toggle("is-running", running);
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
    autoDockStartBtn.hidden = running;
  }
  if (autoDockStopBtn) {
    autoDockStopBtn.hidden = !running;
  }

  if (running || state.autoDockOpen) {
    if (state.sseHealthy) {
      ensureAutoCountdown();
      // SSE 健康时停 2s 轮询，倒计时仍本地跑
      if (state.autoPollTimer) {
        window.clearInterval(state.autoPollTimer);
        state.autoPollTimer = null;
      }
    } else {
      ensureAutoPolling();
      ensureAutoCountdown();
    }
  } else if (!state.sseHealthy) {
    stopAutoPolling();
  } else {
    ensureAutoCountdown();
  }
}

function tickAutoCountdown() {
  const status = state.autoScheduler;
  if (!autoDockCountdown) return;
  const targetUnix = status?.next_slot?.at_unix;
  autoDockCountdown.textContent = formatAutoCountdown(targetUnix);
  const countdownSec = getAutoCountdownSeconds(targetUnix);
  const running = String(status?.state || "") === "running";
  const urgent = running && countdownSec !== null && countdownSec > 0 && countdownSec < 60;
  autoDockCountdown.classList.toggle("is-urgent", urgent);
  document.querySelector(".auto-dock-hero")?.classList.toggle("is-urgent", urgent);
  updateAutoCollapsedMeta(status);
}

function ensureAutoCountdown() {
  if (state.autoCountdownTimer) return;
  state.autoCountdownTimer = window.setInterval(tickAutoCountdown, 1000);
}

function ensureAutoPolling() {
  if (state.sseHealthy && state.eventSource) {
    ensureAutoCountdown();
    return;
  }
  if (!state.autoPollTimer) {
    state.autoPollTimer = window.setInterval(() => {
      if (state.sseHealthy && state.eventSource) return;
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
  const ok = await openAppConfirm({
    eyebrow: "定时点击",
    title: "确定停止调度？",
    desc: "停止调度只会停下定时点击监视器，不会取消正在运行的抽奖任务。",
    confirmLabel: "停止调度",
    cancelLabel: "继续运行",
  });
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
  if (jobResultHint) {
    jobResultHint.hidden = true;
    jobResultHint.textContent = "";
  }
  if (jobResultActions) {
    jobResultActions.hidden = true;
    jobResultActions.innerHTML = "";
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
  const needsFailureHelp = job.state === "error" || (joined > 0 && failed > 0) || (joined === 0 && failed > 0);
  const failure = needsFailureHelp ? classifyJobFailure(job) : null;
  if (jobResultHint) {
    if (failure?.hint) {
      jobResultHint.hidden = false;
      jobResultHint.textContent = failure.hint;
    } else {
      jobResultHint.hidden = true;
      jobResultHint.textContent = "";
    }
  }
  if (needsFailureHelp && failure && failure.retryable !== false) {
    state.lastJobAttempt = {
      action: job.action,
      params: { ...(state.lastJobAttempt?.params || {}) },
    };
  }
  renderFailureActions(jobResultActions, failure, job);
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
  if (!statsGrid) return;
  const counts = summary.user_status_counts || {};
  const drawCounts = summary.counts || {};
  const cards = [
    { key: "total", label: "活动总数", value: summary.total_count || 0 },
    { key: "pending", label: "未参加", value: counts["未参加"] || 0 },
    { key: "joined", label: "已参加", value: counts["已参加"] || 0 },
    { key: "ended", label: "已结束", value: counts["已结束"] || 0 },
    { key: "active", label: "进行中", value: drawCounts.active || 0 },
    { key: "new", label: "上次新入库", value: summary.new_count ?? 0 },
  ];
  const previous = state.statValues || {};
  statsGrid.innerHTML = cards
    .map(
      (card, index) => `
      <article class="stat-card is-entering" style="--card-delay:${index * 55}ms" data-stat-key="${card.key}">
        <p class="stat-label">${card.label}</p>
        <p class="stat-value">${previous[card.key] ?? card.value}</p>
      </article>`
    )
    .join("");
  cards.forEach((card) => {
    const valueEl = statsGrid.querySelector(`[data-stat-key="${card.key}"] .stat-value`);
    animateStatValue(valueEl, previous[card.key] ?? card.value, card.value);
  });
  state.statValues = Object.fromEntries(cards.map((card) => [card.key, card.value]));
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
  closeAppConfirm();
}

function requestLogoutConfirm() {
  return openAppConfirm({
    eyebrow: "账号",
    title: "确认退出登录？",
    desc: "退出后将清除本地登录状态，需要重新扫码登录才能继续使用参与、刷新等功能。",
    confirmLabel: "确认退出",
    cancelLabel: "取消",
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
  clearSaveDirty(document.getElementById("save-participate-text"));
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
      const group = button.closest(".participate-mode-group");
      const originalDisabled = button.disabled;
      button.disabled = true;
      group?.classList.add("is-switching");
      button.classList.add("is-pending");
      try {
        const ok = await saveParticipateTextMode(mode);
        if (ok && !prefersReducedMotion()) {
          const active = document.querySelector("[data-participate-mode].active");
          active?.classList.add("is-just-switched");
          window.setTimeout(() => active?.classList.remove("is-just-switched"), 720);
        }
      } catch (error) {
        setInlineFeedback(participateTextFeedback, String(error.message || error), "error");
      } finally {
        group?.classList.remove("is-switching");
        button.classList.remove("is-pending");
        button.disabled = originalDisabled;
      }
    });
  });
}

function bindSettingsDirtyTracking() {
  const participateInput = document.getElementById("participate-text-input");
  const participateSave = document.getElementById("save-participate-text");
  if (participateInput && participateInput.dataset.dirtyBound !== "true") {
    participateInput.dataset.dirtyBound = "true";
    participateInput.addEventListener("input", () => markSaveDirty(participateSave));
  }

  const llmSave = document.getElementById("save-llm-settings");
  ["llm-api-key-input", "llm-base-url-input", "llm-model-name-input"].forEach((id) => {
    const input = document.getElementById(id);
    if (!input || input.dataset.dirtyBound === "true") return;
    input.dataset.dirtyBound = "true";
    input.addEventListener("input", () => markSaveDirty(llmSave));
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
  renderOnboardingPanel();
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
  const button = document.getElementById("save-llm-settings");
  setButtonLoading(button, true, { label: "保存中…" });
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
    setButtonLoading(button, false);
    clearSaveDirty(button);
    flashButtonSuccess(button);
  } catch (error) {
    setButtonLoading(button, false);
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
    setButtonLoading(button, false);
    clearSaveDirty(button);
    flashButtonSuccess(button);
  } catch (error) {
    setButtonLoading(button, false);
    setInlineFeedback(participateTextFeedback, String(error.message || error), "error");
    throw error;
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
    watchAddMidInput?.classList.add("is-shake");
    window.setTimeout(() => watchAddMidInput?.classList.remove("is-shake"), 420);
    return;
  }
  const mid = parseWatchMidInput(rawMid);
  if (mid === null) {
    showWatchMidError("请输入有效的 B 站用户 MID");
    watchAddMidInput?.focus();
    watchAddMidInput?.classList.add("is-shake");
    window.setTimeout(() => watchAddMidInput?.classList.remove("is-shake"), 420);
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
      <article class="source-row" data-source-id="${escapeHtml(source.id)}" style="--row-delay:${index * 40}ms">
        <div class="source-row-index" aria-hidden="true">${escapeHtml(source.id)}</div>
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
          <p class="source-row-meta"><span class="source-link-count">${source.link_count}</span> 条链接 · ${escapeHtml(source.title || "暂无标题")}</p>
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

function renderActivityTableRow(item, index = 0) {
  const title = escapeHtml(item.activity_title || item.prize || "未知活动");
  const statusTone = activityStatusTone(item.activity_status);
  const soon = isLotterySoon(item.lottery_time);
  const typeTone = lotteryTypeTone(item.lottery_type);
  return `
    <tr class="activity-row is-${statusTone}${soon ? " is-soon" : ""}" data-dynamic-id="${escapeHtml(item.dynamic_id || "")}" style="--row-delay:${Math.min(index, 12) * 28}ms">
      <td class="activity-cell">
        <div class="activity-title">${title}</div>
        ${buildActivityLastNote(item)}
      </td>
      <td class="link-cell">${buildActivityLink(item)}</td>
      <td class="chip-cell"><span class="type-chip type-chip--${typeTone}">${escapeHtml(item.lottery_type)}</span></td>
      <td class="heat-cell"><span class="heat-pill${item.heat_missing ? " heat-pill-missing" : ""}">${formatHeat(item)}</span></td>
      <td class="chip-cell"><span class="${badgeClass(item.activity_status)}">${escapeHtml(item.activity_status)}</span></td>
      <td class="time-cell"><span class="time-pill${soon ? " is-soon" : ""}">${escapeHtml(formatLotteryTime(item.lottery_time))}</span></td>
      <td class="chip-cell action-cell">${buildActivityParticipateBtn(item)}</td>
    </tr>`;
}

function renderActivityCard(item, index = 0) {
  const title = escapeHtml(item.activity_title || item.prize || "未知活动");
  const statusTone = activityStatusTone(item.activity_status);
  const ended = statusTone === "ended" ? " is-ended" : "";
  const soon = isLotterySoon(item.lottery_time);
  const typeTone = lotteryTypeTone(item.lottery_type);
  return `
    <article class="activity-card is-${statusTone}${ended}${soon ? " is-soon" : ""}" data-dynamic-id="${escapeHtml(item.dynamic_id || "")}" style="--row-delay:${Math.min(index, 12) * 28}ms">
      <div class="activity-card-head">
        <h3 class="activity-card-title">${title}</h3>
        <span class="${badgeClass(item.activity_status)}">${escapeHtml(item.activity_status)}</span>
      </div>
      ${buildActivityLastNote(item)}
      <div class="activity-card-meta">
        <span class="type-chip type-chip--${typeTone}">${escapeHtml(item.lottery_type)}</span>
        <span class="heat-pill${item.heat_missing ? " heat-pill-missing" : ""}">${formatHeat(item)}</span>
        <span class="time-pill${soon ? " is-soon" : ""}">${escapeHtml(formatLotteryTime(item.lottery_time))}</span>
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
  return `共 <strong class="filter-summary-count">${total}</strong> 条${filterText} · 第 ${page}/${pages} 页`;
}

function flashActivityRows(dynamicIds) {
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

function renderActivities(payload) {
  const items = payload.items || [];

  if (filterResultSummary) {
    filterResultSummary.innerHTML = formatFilterSummary(payload);
    filterResultSummary.hidden = false;
    pulseFilterSummary();
  }

  if (!items.length) {
    activitiesBody.innerHTML = `<tr class="empty-row"><td colspan="7"><div class="activity-empty">没有匹配的活动<span class="activity-empty-hint">试试调整筛选或换个关键词</span></div></td></tr>`;
    if (activitiesCards) {
      activitiesCards.innerHTML = `<div class="activity-empty">没有匹配的活动<span class="activity-empty-hint">试试调整筛选或换个关键词</span></div>`;
    }
  } else {
    activitiesBody.innerHTML = items.map((item, index) => renderActivityTableRow(item, index)).join("");
    if (activitiesCards) {
      activitiesCards.innerHTML = items.map((item, index) => renderActivityCard(item, index)).join("");
    }
    playActivityListEnter();
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
  syncLogDockTone(job);
  if (job.state === "running") {
    toggleLogDock(true);
    scrollJobLogToBottom({ showHint: true });
  } else if (state.logDockOpen) {
    scrollJobLogToBottom({ showHint: false });
  }
  setButtonsDisabled(job.state === "running");
  updateProgressUI(job);
}

function activateSection(sectionId) {
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
  flashFilterPill(activeButton);
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
    if (isActive) flashFilterPill(button);
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
  const bar = document.getElementById("triple-participate-bar");
  const descEl = document.getElementById("triple-participate-desc");
  const targetsEl = document.getElementById("triple-participate-targets");
  const btn = document.getElementById("triple-participate-btn");
  const labelEl = document.getElementById("triple-participate-btn-label");
  if (!btn || !targetsEl || !labelEl) return;

  const count = Number(data?.count) || 0;
  const items = data?.items || [];
  const jobRunning = document.body.classList.contains("job-running");
  const setupOk = isSetupComplete();

  let tone = "blocked";
  if (setupOk && jobRunning) tone = "running";
  else if (setupOk && count > 0) tone = "ready";
  else if (setupOk) tone = "empty";

  if (bar) {
    bar.dataset.tone = tone;
    bar.classList.toggle("is-ready", tone === "ready");
    bar.classList.toggle("is-empty", tone === "empty");
    bar.classList.toggle("is-blocked", tone === "blocked");
    bar.classList.toggle("is-running", tone === "running");
  }

  if (!setupOk) {
    if (descEl) descEl.textContent = "完成登录与 LLM 配置后，可一键并行参与最多 3 个活动";
    targetsEl.innerHTML = `<span class="triple-participate-empty">需先完成登录与 LLM 配置</span>`;
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
      <span class="triple-target-chip is-entering type-${lotteryTypeTone(item.lottery_type)}" style="--chip-delay:${index * 55}ms" title="${escapeHtml(item.activity_title || item.dynamic_id)}">
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
  state.lastJobAttempt = { action, params: { ...params } };
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
        startRealtime();
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
    const code = String(error.code || "");
    if (code === "AUTH_REQUIRED" || message.includes("请先扫码登录")) {
      showToast("请先扫码登录", "info", "完成登录与 LLM 配置后才能使用项目功能");
    } else if (
      code === "LLM_NOT_READY" ||
      message.includes("连接测试") ||
      message.includes("配置并通过连接测试") ||
      /未配置\s*LLM|配置 LLM/i.test(message)
    ) {
      showToast("请先测试 LLM 连接", "info", "保存配置后点击「测试连接」，通过后才能使用项目功能");
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
  const current = await fetchJSON("/api/jobs/current");
  state.currentJob = current;
  updateJobUI(current);
  startRealtime();
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
  } else if (job.state === "cancelled") {
    showToast(sanitizeUserText(job.message) || "任务已取消", "info");
  } else if (job.state === "error") {
    if (job.action === "login" && !state.qrcodeDismissed) {
      renderQrcodeLoginState({
        ...job,
        result: { ...(job.result || {}), login_phase: "error" },
        message: sanitizeUserText(job.message) || "登录失败，请重试",
      });
    } else {
      const failure = classifyJobFailure(job);
      if (failure.severity === "info") {
        showToast(failure.message, "info", failure.hint || formatToastDetail(job));
      } else {
        showFailureToast(failure, job);
      }
    }
  }

  const finishedDynamicIds = collectFinishedDynamicIds(job);
  try {
    await loadSummary();
    await syncProjectState();
    await loadActivities();
    if (job.action === "refresh_watch") {
      await loadWatchUsers();
      if (job.state === "success") pulseWatchSyncCard();
    }
    if (job.action === "refresh_source" && job.state === "success") {
      const sourceId = state.lastJobAttempt?.params?.source_id;
      flashSourceRow(sourceId);
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
        setSourceRowUpdating(params.source_id, true);
      }
      try {
        if (action === "refresh_all") {
          const confirmed = await confirmRefreshAll();
          if (!confirmed) {
            setButtonLoading(button, false);
            return;
          }
        }
        await startJob(action, params);
      } catch (error) {
        const failure = classifyFailureText(error.message || error, action);
        if (failure.severity === "info") {
          showToast(failure.message, "info", failure.hint);
        } else {
          showFailureToast(failure, { action, params });
        }
        setButtonLoading(button, false);
        if (action === "refresh_source") {
          setSourceRowUpdating(params.source_id, false);
        }
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

function markSseActive() {
  state.sseLastActive = Date.now();
}

function stopSseWatchdog() {
  if (state.sseWatchdog) {
    window.clearInterval(state.sseWatchdog);
    state.sseWatchdog = null;
  }
}

function startSseWatchdog() {
  stopSseWatchdog();
  state.sseWatchdog = window.setInterval(() => {
    if (!state.sseHealthy) return;
    if (Date.now() - state.sseLastActive > SSE_WATCHDOG_MS) {
      console.warn("SSE heartbeat timeout, fallback to polling");
      fallbackToPolling("heartbeat-timeout");
    }
  }, 5000);
}

function closeEventSource() {
  if (state.eventSource) {
    try {
      state.eventSource.close();
    } catch {
      /* ignore */
    }
    state.eventSource = null;
  }
  stopSseWatchdog();
  state.sseHealthy = false;
}

function fallbackToPolling(reason) {
  closeEventSource();
  // 浏览器不支持 EventSource 时不要循环重连
  if (reason !== "no-eventsource") {
    if (state.sseReconnectTimer) {
      window.clearTimeout(state.sseReconnectTimer);
    }
    state.sseReconnectTimer = window.setTimeout(() => {
      state.sseReconnectTimer = null;
      startRealtime();
    }, SSE_RECONNECT_MS);
  }
  const job = state.currentJob;
  if (job?.state === "running") startPolling();
  if (state.autoDockOpen || state.autoScheduler?.state === "running") {
    ensureAutoPolling();
  }
}

function applyRunningJobView(job) {
  state.currentJob = job;
  updateJobUI(job);
  if (job.state === "running" && job.action === "login" && !state.qrcodeDismissed) {
    ensureQrcodeModalVisible();
    renderQrcodeLoginState(job);
    const refreshedAt = Number(job.result?.qrcode_refreshed_at) || 0;
    if (refreshedAt && refreshedAt !== state.lastQrcodeRefresh) {
      state.lastQrcodeRefresh = refreshedAt;
      loadQrcodeImage(refreshedAt);
    }
  }
}

async function finishJobOnce(job) {
  const key = `${job.id || ""}:${job.action || ""}:${job.state || ""}:${job.finished_at || ""}`;
  if (key && key === state.lastFinishedJobKey) return;
  state.lastFinishedJobKey = key;
  state.currentJob = job;
  updateJobUI(job);

  if (job.action === "login" && (job.state === "cancelled" || job.state === "idle")) {
    stopJobPolling();
    setButtonsDisabled(false);
    hideQrcodeModal(false);
    if (job.state === "cancelled") {
      showToast(sanitizeUserText(job.message) || "已取消扫码登录", "info");
    }
    return;
  }
  stopJobPolling();
  try {
    await handleJobCompletion(job);
  } catch (error) {
    console.error("finishJobOnce failed", error);
  }
}

function mergeJobProgress(payload) {
  const base = state.currentJob || {};
  return {
    ...base,
    id: payload.id ?? base.id,
    state: "running",
    action: base.action || "",
    label: base.label || "",
    source: base.source || "ui",
    progress_step: payload.step ?? base.progress_step ?? 0,
    progress_total: payload.total ?? base.progress_total ?? 0,
    message: payload.message || base.message || "",
    progress_message: payload.message || base.progress_message || "",
    log: base.log || "",
    result: { ...(base.result || {}), ...(payload.result || {}) },
  };
}

function appendJobLogChunk(chunk) {
  const base = state.currentJob || { state: "running", log: "" };
  const current = String(base.log || "").trim();
  const next = current ? `${current}\n${chunk}` : chunk;
  state.currentJob = { ...base, log: next, state: base.state || "running" };
  updateJobUI(state.currentJob);
}

function autoLogKey(row) {
  return `${row?.ts || ""}|${row?.level || ""}|${row?.message || ""}`;
}

function mergeAutoLogs(existing, incoming) {
  const map = new Map();
  for (const row of existing || []) {
    if (!row) continue;
    map.set(autoLogKey(row), row);
  }
  for (const row of incoming || []) {
    if (!row) continue;
    map.set(autoLogKey(row), row);
  }
  return Array.from(map.values()).slice(-80);
}

function handleSseMessage(eventName, payload) {
  markSseActive();
  if (eventName === "heartbeat") return;

  if (eventName === "job.snapshot" || eventName === "job.created") {
    const job = {
      ...(state.currentJob || {}),
      ...payload,
      state: payload.state || (eventName === "job.created" ? "running" : payload.state),
    };
    if (eventName === "job.created") {
      // 新任务不得沿用上一任务的 log/result/进度
      job.log = "";
      job.result = payload.result && typeof payload.result === "object" ? payload.result : {};
      job.progress_step = payload.progress_step ?? 0;
      job.progress_total = payload.progress_total ?? 0;
      job.finished_at = null;
      job.message = payload.message || "任务已启动";
      state.lastFinishedJobKey = "";
    }
    if (job.state === "running") {
      applyRunningJobView(job);
    } else {
      state.currentJob = job;
      updateJobUI(job);
    }
    return;
  }

  if (eventName === "job.progress") {
    applyRunningJobView(mergeJobProgress(payload));
    return;
  }

  if (eventName === "job.log") {
    if (payload?.chunk) appendJobLogChunk(String(payload.chunk));
    return;
  }

  if (eventName === "job.terminal") {
    const job = {
      ...(state.currentJob || {}),
      ...payload,
      state: payload.state,
      id: payload.id ?? state.currentJob?.id,
    };
    void finishJobOnce(job);
    return;
  }

  if (eventName === "auto.snapshot") {
    if (Array.isArray(payload.logs)) {
      state.autoLogs = mergeAutoLogs(state.autoLogs, payload.logs);
    }
    renderAutoDock({ ...payload, logs: state.autoLogs });
    return;
  }

  if (eventName === "auto.log") {
    const row = {
      ts: payload.log_ts || "",
      level: payload.level || "info",
      message: payload.message || "",
    };
    state.autoLogs = mergeAutoLogs(state.autoLogs, [row]);
    if (state.autoScheduler) {
      renderAutoDock({ ...state.autoScheduler, logs: state.autoLogs });
    }
  }
}

function startRealtime() {
  if (typeof EventSource === "undefined") {
    fallbackToPolling("no-eventsource");
    return;
  }
  if (state.eventSource && state.sseHealthy) return;
  // 已有连接正在建立时不要重复创建
  if (state.eventSource && state.eventSource.readyState === EventSource.CONNECTING) return;

  closeEventSource();
  try {
    const es = new EventSource("/api/events");
    state.eventSource = es;
    const bind = (name) => {
      es.addEventListener(name, (ev) => {
        try {
          const payload = JSON.parse(ev.data || "{}");
          state.sseHealthy = true;
          handleSseMessage(name, payload);
          // SSE 恢复后停掉 Job REST 轮询；Auto 倒计时保留
          if (state.polling) stopJobPolling();
          if (state.autoPollTimer) {
            window.clearInterval(state.autoPollTimer);
            state.autoPollTimer = null;
          }
        } catch (error) {
          console.error("SSE parse failed", name, error);
        }
      });
    };
    [
      "heartbeat",
      "job.snapshot",
      "job.created",
      "job.progress",
      "job.log",
      "job.terminal",
      "auto.snapshot",
      "auto.log",
    ].forEach(bind);
    es.onopen = () => {
      state.sseHealthy = true;
      markSseActive();
      startSseWatchdog();
      stopJobPolling();
      // 保留倒计时，仅停 REST 轮询
      if (state.autoPollTimer) {
        window.clearInterval(state.autoPollTimer);
        state.autoPollTimer = null;
      }
      ensureAutoCountdown();
    };
    es.onerror = () => {
      if (state.sseHealthy) {
        fallbackToPolling("eventsource-error");
        return;
      }
      // 尚未建连成功：关闭后稍后重试，并立刻用轮询兜底
      closeEventSource();
      const job = state.currentJob;
      if (job?.state === "running") startPolling();
      if (state.autoDockOpen || state.autoScheduler?.state === "running") {
        ensureAutoPolling();
      }
      if (!state.sseReconnectTimer) {
        state.sseReconnectTimer = window.setTimeout(() => {
          state.sseReconnectTimer = null;
          startRealtime();
        }, SSE_RECONNECT_MS);
      }
    };
    markSseActive();
    startSseWatchdog();
  } catch (error) {
    console.error(error);
    fallbackToPolling("eventsource-throw");
  }
}

function startPolling() {
  // H2：SSE 健康时不双通道
  if (state.sseHealthy && state.eventSource) return;
  if (state.polling) return;
  const poll = async () => {
    if (state.sseHealthy && state.eventSource) {
      stopJobPolling();
      return;
    }
    try {
      const job = await fetchJSON("/api/jobs/current");
      state.currentJob = job;
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
      stopJobPolling();
      await finishJobOnce(job);
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
  bindSettingsDirtyTracking();
  bindLlmApiKeyToggle();
  bindWatchUsers();
  bindOnboardingPanel();
  bindActionButtons();
  await syncProjectState();
  try {
    const job = await loadSummary();
    if (job) state.currentJob = job;
    await fetchAutoStatus().catch(() => {});
    loadWatchUsers().catch(() => {});
    await loadActivities();
    startRealtime();
    if (job?.state === "running") startPolling();
  } catch (error) {
    showToast(sanitizeUserText(error.message || error) || "数据加载失败", "error");
  }
  playOverviewEnter();
}

function initSystemPreferences() {
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

const SIDEBAR_ANIM_MS = 400;
const THEME_ANIM_MS = 320;

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

function applyTheme(theme, { animate = true } = {}) {
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

window.addEventListener("pageshow", (event) => {
  if (!event.persisted) return;
  syncProjectState().catch((error) => {
    showToast(String(error.message || error), "error");
  });
});

init().catch((error) => {
  showToast(String(error.message || error), "error");
});
