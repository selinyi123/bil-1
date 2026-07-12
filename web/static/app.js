const state = {
  page: 1,
  pageSize: 30,
  filters: { q: "", type: "", status: "", draw: "active" },
  polling: null,
  logDockOpen: false,
};

const jobPill = document.getElementById("job-pill");
const jobMessage = document.getElementById("job-message");
const jobLog = document.getElementById("job-log");
const statsGrid = document.getElementById("stats-grid");
const sourceGrid = document.getElementById("source-grid");
const accountCard = document.getElementById("account-card");
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
      throw new Error(text || response.statusText);
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
    </div>`;
  toastStack.appendChild(toast);
  window.setTimeout(() => {
    toast.classList.add("toast-hide");
    window.setTimeout(() => toast.remove(), 280);
  }, type === "error" ? 5200 : 3800);
}

function showQrcodeModal() {
  if (!qrcodeModal) return;
  qrcodeModal.hidden = false;
  document.body.classList.add("modal-open");
  if (qrcodeStatus) qrcodeStatus.textContent = "等待扫码…";
  if (qrcodeImg) qrcodeImg.src = `/api/login/qrcode?t=${Date.now()}`;
}

function hideQrcodeModal() {
  if (!qrcodeModal) return;
  qrcodeModal.hidden = true;
  document.body.classList.remove("modal-open");
}

function setLogDockOpen(open) {
  state.logDockOpen = open;
  if (!logDockPanel || !logDockToggle) return;
  logDockPanel.hidden = !open;
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

function renderAccount(account) {
  if (!account.logged_in) {
    accountCard.innerHTML = `
      <div class="account-meta">
        <h3>未登录</h3>
        <p>${escapeHtml(account.message || "请先扫码登录")}</p>
        <span class="account-status warn">需重新扫码登录</span>
      </div>`;
    return;
  }

  const avatar = account.face
    ? `<img class="account-avatar" src="${escapeHtml(account.face)}" alt="头像" referrerpolicy="no-referrer" crossorigin="anonymous" />`
    : `<div class="account-avatar account-avatar-fallback"></div>`;
  accountCard.innerHTML = `
    ${avatar}
    <div class="account-meta">
      <h3>${escapeHtml(account.uname || "B站用户")}</h3>
      <p>关注 ${account.following ?? "—"} · 动态 ${account.dynamic_count ?? "—"} · 私信 ${account.unread_messages ?? "—"}</p>
      <span class="account-status ${account.expired ? "warn" : "ok"}">${account.expired ? "需重新扫码登录" : "已登录"}</span>
    </div>`;
}

async function loadAccount() {
  const account = await fetchJSON("/api/account", { timeoutMs: 20000 });
  renderAccount(account);
  return account;
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
          ? `<button class="btn btn-primary btn-compact" data-action="participate" data-dynamic-id="${escapeHtml(item.dynamic_id)}">参与</button>`
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
  const label = job.state === "running" ? `运行中 · ${job.label}` : job.label || "空闲";
  jobPill.textContent = label;
  jobPill.className = `job-pill ${job.state || "idle"}`;
  jobMessage.textContent = job.message || "暂无任务";
  jobLog.textContent = job.log || "";
  if (logDockBadge) {
    const running = job.state === "running";
    logDockBadge.hidden = !running;
    logDockBadge.textContent = running ? "运行中" : "";
  }
  if (job.state === "running") {
    toggleLogDock(true);
  }
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
  logDockToggle?.addEventListener("click", () => toggleLogDock());
  document.getElementById("log-dock-collapse")?.addEventListener("click", () => toggleLogDock(false));
  document.getElementById("qrcode-close")?.addEventListener("click", hideQrcodeModal);
  document.getElementById("qrcode-backdrop")?.addEventListener("click", hideQrcodeModal);
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
  const actionNames = { login: "扫码登录", refresh_all: "一键更新", participate: "参与活动" };
  showToast(`正在启动${actionNames[action] || action}…`, "running");
  toggleLogDock(true);
  await fetchJSON("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, params }),
  });
  if (action === "login") showQrcodeModal();
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
      if (job.action === "login") {
        showQrcodeModal();
        if (qrcodeStatus) qrcodeStatus.textContent = job.message || "等待扫码确认…";
      }
      return;
    }
    const finishedDynamicId = job.action === "participate" ? job.result?.dynamic_id : null;
    if (job.state === "success") {
      const detail = job.log ? job.log.split("\n").slice(0, 4).join(" · ") : "";
      showToast(job.message || "任务完成", "success", detail);
    } else if (job.state === "error") {
      showToast(job.message || "任务失败", "error", job.log || "");
    }
    window.clearInterval(state.polling);
    state.polling = null;
    await loadSummary();
    await loadAccount();
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
    if (job.action === "login") hideQrcodeModal();
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

document.getElementById("refresh-account").addEventListener("click", async () => {
  const button = document.getElementById("refresh-account");
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "刷新中…";
  try {
    await loadAccount();
    showToast("账号信息已更新", "success");
  } catch (error) {
    showToast(String(error.message || error), "error");
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
});

async function init() {
  bindNavigation();
  bindFilterPills();
  bindActionButtons();
  await loadAccount();
  const job = await loadSummary();
  await loadActivities();
  if (job?.state === "running") startPolling();
}

init().catch((error) => {
  showToast(String(error.message || error), "error");
  jobPill.className = "job-pill error";
});
