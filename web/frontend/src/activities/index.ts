/* eslint-disable */
/** Migrated from web/static/app.js — logic preserved. */

import { state } from "../state";
import { fetchJSON } from "../api/client";
import { isSetupComplete } from "../account/index";
import { activitiesBody, activitiesCards, filterDrawWindowHint, filterResultSummary, pagination, statsGrid } from "../dom";
import { bindActionButtons, updateJobUI } from "../jobs/index";
import { showToast } from "../shell/toast";
import { activityStatusTone, badgeClass, formatFilterSummary, formatHeat, formatLastParticipation, formatLotteryTime, isLotterySoon, lotteryTypeTone } from "../utils/format";
import { animateStatValue, flashFilterPill, playActivityListEnter, pulseFilterSummary } from "../utils/motion";
import { escapeHtml, safeUrl, truncateText } from "../utils/text";
import { renderSources } from "../watch/index";
import type { JobStatus } from "../types";
import type { LastParticipation } from "../utils/format";

interface ActivityItem {
  dynamic_id?: unknown;
  activity_title?: string;
  prize?: string;
  activity_status?: string;
  lottery_type?: string;
  lottery_time?: string | null;
  source_url?: string;
  can_participate?: boolean;
  heat_missing?: boolean;
  repost_count?: number | string;
  last_participation?: LastParticipation | null;
}

interface ActivitiesPayload {
  items?: ActivityItem[];
  page?: number | string;
  pages?: number | string;
  total?: number | string;
  triple_targets?: TripleTargetsData | null;
}

interface TripleTargetItem {
  dynamic_id?: unknown;
  activity_title?: string;
  lottery_type?: string;
  activity_status?: string;
}

interface TripleTargetsData {
  count: number;
  limit: number;
  items: unknown[];
}

interface SummaryPayload {
  user_status_counts?: Record<string, number>;
  counts?: Record<string, number>;
  total_count?: number;
  new_count?: number;
  sources?: Array<{ id: string | number }> | null;
  job?: JobStatus | null;
}

export function renderStats(summary: SummaryPayload) {
  if (!statsGrid) return;
  const counts: Record<string, number> = summary.user_status_counts || {};
  const drawCounts: Record<string, number> = summary.counts || {};
  const cards = [
    { key: "total", label: "活动总数", value: summary.total_count || 0 },
    { key: "pending", label: "未参加", value: counts["未参加"] || 0 },
    { key: "joined", label: "已参加", value: counts["已参加"] || 0 },
    { key: "ended", label: "已结束", value: counts["已结束"] || 0 },
    { key: "active", label: "进行中", value: drawCounts.active || 0 },
    { key: "new", label: "上次新入库", value: summary.new_count ?? 0 },
  ];
  const previous: Record<string, number> = state.statValues || {};
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
    const valueEl = statsGrid!.querySelector<HTMLElement>(`[data-stat-key="${card.key}"] .stat-value`);
    animateStatValue(valueEl, previous[card.key] ?? card.value, card.value);
  });
  state.statValues = Object.fromEntries(cards.map((card) => [card.key, card.value] as const));
}

export function buildActivityParticipateBtn(item: ActivityItem) {
  if (item.can_participate) {
    return `<button class="btn btn-primary btn-compact btn-pill" data-action="participate" data-dynamic-id="${escapeHtml(item.dynamic_id)}">参与</button>`;
  }
  return `<span class="caption">—</span>`;
}

export function buildActivityLastNote(item: ActivityItem) {
  if (!item.last_participation) return "";
  return `<div class="last-result ${escapeHtml(item.last_participation.status || "")}">上次：${escapeHtml(formatLastParticipation(item.last_participation))}</div>`;
}

export function buildActivityLink(item: ActivityItem) {
  if (item.source_url) {
    return `<a class="activity-link" href="${escapeHtml(safeUrl(item.source_url))}" target="_blank" rel="noopener">打开动态</a>`;
  }
  return `<span class="caption">—</span>`;
}

export function renderActivityTableRow(item: ActivityItem, index = 0) {
  const title = escapeHtml(item.activity_title || item.prize || "未知活动");
  const statusTone = activityStatusTone(item.activity_status || "");
  const soon = isLotterySoon(item.lottery_time);
  const typeTone = lotteryTypeTone(item.lottery_type || "");
  return `
    <tr class="activity-row is-${statusTone}${soon ? " is-soon" : ""}" data-dynamic-id="${escapeHtml(item.dynamic_id || "")}" style="--row-delay:${Math.min(index, 12) * 28}ms">
      <td class="activity-cell">
        <div class="activity-title">${title}</div>
        ${buildActivityLastNote(item)}
      </td>
      <td class="link-cell">${buildActivityLink(item)}</td>
      <td class="chip-cell"><span class="type-chip type-chip--${typeTone}">${escapeHtml(item.lottery_type)}</span></td>
      <td class="heat-cell"><span class="heat-pill${item.heat_missing ? " heat-pill-missing" : ""}">${formatHeat(item)}</span></td>
      <td class="chip-cell"><span class="${badgeClass(item.activity_status || "")}">${escapeHtml(item.activity_status)}</span></td>
      <td class="time-cell"><span class="time-pill${soon ? " is-soon" : ""}">${escapeHtml(formatLotteryTime(item.lottery_time))}</span></td>
      <td class="chip-cell action-cell">${buildActivityParticipateBtn(item)}</td>
    </tr>`;
}

export function renderActivityCard(item: ActivityItem, index = 0) {
  const title = escapeHtml(item.activity_title || item.prize || "未知活动");
  const statusTone = activityStatusTone(item.activity_status || "");
  const ended = statusTone === "ended" ? " is-ended" : "";
  const soon = isLotterySoon(item.lottery_time);
  const typeTone = lotteryTypeTone(item.lottery_type || "");
  return `
    <article class="activity-card is-${statusTone}${ended}${soon ? " is-soon" : ""}" data-dynamic-id="${escapeHtml(item.dynamic_id || "")}" style="--row-delay:${Math.min(index, 12) * 28}ms">
      <div class="activity-card-head">
        <h3 class="activity-card-title">${title}</h3>
        <span class="${badgeClass(item.activity_status || "")}">${escapeHtml(item.activity_status)}</span>
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

// 竞态防护：翻页/筛选快速切换时，只接受最新一次请求的响应
let activitiesLoadSeq = 0;

function renderActivitiesLoading() {
  const html = `<tr class="empty-row"><td colspan="7"><div class="activity-empty activity-loading">正在加载活动…</div></td></tr>`;
  activitiesBody!.innerHTML = html;
  if (activitiesCards) {
    activitiesCards.innerHTML = `<div class="activity-empty activity-loading">正在加载活动…</div>`;
  }
}

function renderActivitiesError(message: unknown) {
  const text = escapeHtml(String(message || "未知错误"));
  const html = `<tr class="empty-row"><td colspan="7"><div class="activity-empty activity-error"><span>活动加载失败：${text}</span><button type="button" class="btn btn-secondary btn-compact btn-pill" id="activities-retry">重试</button></div></td></tr>`;
  activitiesBody!.innerHTML = html;
  if (activitiesCards) {
    activitiesCards.innerHTML = `<div class="activity-empty activity-error">活动加载失败：${text}</div>`;
  }
  document.getElementById("activities-retry")?.addEventListener("click", () => {
    state.page = 1;
    loadActivities();
  });
}

export function renderActivities(payload: ActivitiesPayload) {
  const items = payload.items || [];

  if (filterResultSummary) {
    filterResultSummary.innerHTML = formatFilterSummary(payload);
    filterResultSummary.hidden = false;
    pulseFilterSummary();
  }

  if (!items.length) {
    activitiesBody!.innerHTML = `<tr class="empty-row"><td colspan="7"><div class="activity-empty">没有匹配的活动<span class="activity-empty-hint">试试调整筛选或换个关键词</span></div></td></tr>`;
    if (activitiesCards) {
      activitiesCards.innerHTML = `<div class="activity-empty">没有匹配的活动<span class="activity-empty-hint">试试调整筛选或换个关键词</span></div>`;
    }
  } else {
    activitiesBody!.innerHTML = items.map((item, index) => renderActivityTableRow(item, index)).join("");
    if (activitiesCards) {
      activitiesCards.innerHTML = items.map((item, index) => renderActivityCard(item, index)).join("");
    }
    playActivityListEnter();
  }

  const page = Number(payload.page) || 1;
  const pages = Math.max(1, Number(payload.pages) || 1);
  const total = Number(payload.total) || 0;
  pagination!.innerHTML = `
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

export async function loadSummary() {
  const summary = await fetchJSON<SummaryPayload>("/api/summary");
  renderStats(summary);
  renderSources(summary.sources);
  updateJobUI(summary.job || { state: "idle" });
  return summary.job;
}

export function setFilterPillGroup(selector: string, activeButton: Element) {
  document.querySelectorAll(selector).forEach((item) => {
    const active = item === activeButton;
    item.classList.toggle("active", active);
    item.setAttribute("aria-pressed", active ? "true" : "false");
  });
  flashFilterPill(activeButton as HTMLElement);
}

export function setStatusFilter(value: string) {
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

export function setDrawWindowFilter(value: string) {
  state.filters.drawWindow = value || "";
  document.querySelectorAll("[data-filter-draw-window]").forEach((button) => {
    const isActive = (button.getAttribute("data-filter-draw-window") || "") === state.filters.drawWindow;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-pressed", isActive ? "true" : "false");
    if (isActive) flashFilterPill(button as HTMLElement);
  });
  if (filterDrawWindowHint) {
    filterDrawWindowHint.hidden = !state.filters.drawWindow;
  }
}

export function updateDrawWindowHint() {
  if (!filterDrawWindowHint || !state.filters.drawWindow) return;
  filterDrawWindowHint.textContent = "仅筛选你已参加、且 3 天内即将开奖的活动";
}

export function buildActivityFilterQueryParams() {
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

export function renderTripleParticipateBar(data: TripleTargetsData | null | undefined) {
  const bar = document.getElementById("triple-participate-bar");
  const descEl = document.getElementById("triple-participate-desc");
  const targetsEl = document.getElementById("triple-participate-targets");
  const btn = document.getElementById("triple-participate-btn");
  const labelEl = document.getElementById("triple-participate-btn-label");
  if (!btn || !targetsEl || !labelEl) return;
  const btnEl = btn as HTMLButtonElement;

  const count = Number(data?.count) || 0;
  const items = (data?.items || []) as TripleTargetItem[];
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
    btnEl.disabled = true;
    labelEl.textContent = "三连参与";
    return;
  }

  if (count <= 0) {
    if (descEl) descEl.textContent = "当前筛选列表下没有可参与的未参加活动";
    targetsEl.innerHTML = `<span class="triple-participate-empty">暂无可参与目标</span>`;
    btnEl.disabled = true;
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
      <span class="triple-target-chip is-entering type-${lotteryTypeTone(item.lottery_type || "")}" style="--chip-delay:${index * 55}ms" title="${escapeHtml(item.activity_title || item.dynamic_id)}">
        <span class="triple-target-chip-index">${index + 1}</span>
        <span class="triple-target-chip-title">${escapeHtml(truncateText(item.activity_title || item.dynamic_id))}</span>
        <span class="triple-target-chip-type">${escapeHtml(item.lottery_type || "")}</span>
      </span>`
    )
    .join("");
  btnEl.disabled = jobRunning;
  labelEl.textContent = count >= 3 ? "三连参与 (3)" : `三连参与 (${count})`;
}

export function buildActivityFilterJobParams() {
  const params: Record<string, string> = {};
  if (state.filters.draw) params.draw = state.filters.draw;
  if (state.filters.q) params.q = state.filters.q;
  if (state.filters.type) params.lottery_type = state.filters.type;
  if (state.filters.status) params.status = state.filters.status;
  if (state.filters.drawWindow) params.draw_window = state.filters.drawWindow;
  if (state.filters.sort) params.sort = state.filters.sort;
  if (state.filters.order) params.order = state.filters.order;
  return params;
}

export function getActiveFilterKey() {
  return JSON.stringify(state.filters);
}

export function computeTripleTargetsFromItems(items: ActivityItem[] | null | undefined) {
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

export function resolveTripleTargets(payload: ActivitiesPayload) {
  if (payload?.triple_targets && Array.isArray(payload.triple_targets.items)) {
    return payload.triple_targets;
  }
  if (state.page === 1) {
    return computeTripleTargetsFromItems(payload?.items || []);
  }
  return null;
}

export function applyTripleTargets(data: TripleTargetsData | null) {
  state.tripleTargets = data || { count: 0, limit: 3, items: [] };
  state.tripleFilterKey = getActiveFilterKey();
  renderTripleParticipateBar(state.tripleTargets);
}

export async function loadTripleTargets() {
  try {
    const query = buildActivityFilterQueryParams().toString();
    const url = query ? `/api/activities/triple-targets?${query}` : "/api/activities/triple-targets";
    const data = await fetchJSON<TripleTargetsData>(url);
    applyTripleTargets(data);
  } catch {
    applyTripleTargets({ count: 0, limit: 3, items: [] });
  }
}

export async function loadActivities() {
  const seq = ++activitiesLoadSeq;
  renderActivitiesLoading();
  const filterKey = getActiveFilterKey();
  const params = new URLSearchParams({
    page: String(state.page),
    page_size: String(state.pageSize),
  });
  buildActivityFilterQueryParams().forEach((value, key) => params.set(key, value));
  try {
    const payload = await fetchJSON<ActivitiesPayload>(`/api/activities?${params.toString()}`);
    if (seq !== activitiesLoadSeq) return; // 过期响应丢弃
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
    if (seq !== activitiesLoadSeq) return; // 过期失败也丢弃
    renderActivitiesError(error instanceof Error ? error.message || error : error);
  }
}

export function bindFilterPills() {
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
  let searchTimer: number | null = null;
  filterQ.addEventListener("input", () => {
    window.clearTimeout(searchTimer ?? undefined);
    searchTimer = window.setTimeout(() => {
      state.page = 1;
      state.filters.q = (filterQ as HTMLInputElement).value.trim();
      loadActivities();
    }, 320);
  });
}
