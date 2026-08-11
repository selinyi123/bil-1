import { fetchJSON } from "../api/client";
import { sourceGrid } from "../dom";
import { bindActionButtons } from "../jobs/index";
import { openAppConfirm } from "../shell/confirm";
import { showToast } from "../shell/toast";
import { escapeHtml } from "../utils/text";

interface SourceSettingsPayload {
  ok?: boolean;
  ds8?: { dynamic_ids?: string[]; count?: number };
  ds9?: { tags?: string[]; count?: number };
  ds10?: {
    entries?: Array<{ id: string; kind: string; display: string }>;
    count?: number;
    file_scope?: string;
  };
}

let sourceSettingsLoadSeq = 0;

function panel(): HTMLElement | null {
  return document.getElementById("managed-source-settings");
}

function buildPanel(): HTMLElement {
  const wrap = document.createElement("article");
  wrap.className = "panel managed-source-settings";
  wrap.id = "managed-source-settings";
  wrap.innerHTML = `
    <div class="settings-panel-head">
      <div class="settings-panel-intro">
        <p class="eyebrow">Managed Sources</p>
        <h2 class="section-title">可管理数据源</h2>
        <p class="section-desc">DS-8 / DS-9 使用 typed 配置保存；DS-10 以脱敏条目增删，带 token 的完整 URL 不会从后端回显。</p>
      </div>
    </div>
    <div class="managed-source-grid">
      <section class="managed-source-card" data-managed-source="DS-8">
        <div class="managed-source-head">
          <div><span class="source-kicker">DS-8</span><h3>手动动态清单</h3></div>
          <span class="source-count" data-ds8-count>—</span>
        </div>
        <p class="caption">每行一个 18–19 位动态 ID 或 B 站动态链接；保存时自动规范化和去重。</p>
        <textarea class="textarea managed-source-textarea" rows="7" data-ds8-input spellcheck="false" placeholder="https://www.bilibili.com/opus/123456789012345678"></textarea>
        <div class="settings-action-row">
          <button type="button" class="btn btn-primary btn-pill" data-source-setting-action="save-ds8">保存 DS-8</button>
          <button type="button" class="btn btn-secondary btn-pill" data-action="refresh_source" data-source-id="DS-8">保存后更新此源</button>
        </div>
      </section>

      <section class="managed-source-card" data-managed-source="DS-9">
        <div class="managed-source-head">
          <div><span class="source-kicker">DS-9</span><h3>话题源</h3></div>
          <span class="source-count" data-ds9-count>—</span>
        </div>
        <p class="caption">每行一个话题；首尾 # 会在保存时规范化。内容变化后下一次刷新会触发增量扫描。</p>
        <textarea class="textarea managed-source-textarea" rows="7" data-ds9-input spellcheck="false" placeholder="抽奖\n福利"></textarea>
        <div class="settings-action-row">
          <button type="button" class="btn btn-primary btn-pill" data-source-setting-action="save-ds9">保存 DS-9</button>
          <button type="button" class="btn btn-secondary btn-pill" data-action="refresh_source" data-source-id="DS-9">保存后更新此源</button>
        </div>
      </section>

      <section class="managed-source-card managed-source-card-wide" data-managed-source="DS-10">
        <div class="managed-source-head">
          <div><span class="source-kicker">DS-10</span><h3>外部 API / JSON 源</h3></div>
          <span class="source-count" data-ds10-count>—</span>
        </div>
        <p class="caption">HTTP(S) URL 可直接添加；file:// 通过 Web 新增时只允许位于 BINGGO_HOME 内。已有 URL 的认证信息与 query value 仅显示为 ***。</p>
        <div class="managed-source-entry-list" data-ds10-list></div>
        <div class="managed-source-add-row">
          <input class="input" type="password" autocomplete="new-password" data-ds10-input placeholder="https://example.com/lottery.json?token=...">
          <button type="button" class="btn btn-primary btn-pill" data-source-setting-action="add-ds10">添加外部源</button>
        </div>
        <p class="caption" data-ds10-scope></p>
        <div class="settings-action-row">
          <button type="button" class="btn btn-secondary btn-pill" data-action="refresh_source" data-source-id="DS-10">更新 DS-10</button>
        </div>
      </section>
    </div>
    <p class="inline-feedback" data-source-settings-feedback hidden></p>`;
  return wrap;
}

function setFeedback(text: string, tone = "info"): void {
  const el = panel()?.querySelector<HTMLElement>("[data-source-settings-feedback]");
  if (!el) return;
  el.hidden = !text;
  el.textContent = text;
  el.dataset.tone = tone;
}

function lineValues(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function disableMutations(disabled: boolean): void {
  panel()?.querySelectorAll<HTMLButtonElement>("[data-source-setting-action]").forEach((button) => {
    button.disabled = disabled;
  });
}

function renderDs10(data: NonNullable<SourceSettingsPayload["ds10"]>): void {
  const wrap = panel();
  if (!wrap) return;
  const entries = data.entries || [];
  const list = wrap.querySelector<HTMLElement>("[data-ds10-list]");
  const count = wrap.querySelector<HTMLElement>("[data-ds10-count]");
  const scope = wrap.querySelector<HTMLElement>("[data-ds10-scope]");
  if (count) count.textContent = `${Number(data.count ?? entries.length)} 个来源`;
  if (scope) scope.textContent = data.file_scope ? `Web file:// 安全范围：${data.file_scope}` : "";
  if (!list) return;
  if (!entries.length) {
    list.innerHTML = '<p class="caption">尚未配置外部源。</p>';
    return;
  }
  list.innerHTML = entries
    .map(
      (entry) => `
        <div class="managed-source-entry" data-source-entry-id="${escapeHtml(entry.id)}">
          <span class="source-kind">${escapeHtml(entry.kind.toUpperCase())}</span>
          <code title="${escapeHtml(entry.display)}">${escapeHtml(entry.display)}</code>
          <button type="button" class="btn btn-ghost btn-compact btn-pill" data-source-setting-action="remove-ds10" data-source-entry-id="${escapeHtml(entry.id)}">删除</button>
        </div>`,
    )
    .join("");
}

function render(data: SourceSettingsPayload): void {
  const wrap = panel();
  if (!wrap) return;
  const ds8 = data.ds8 || {};
  const ds9 = data.ds9 || {};
  const ds8Input = wrap.querySelector<HTMLTextAreaElement>("[data-ds8-input]");
  const ds9Input = wrap.querySelector<HTMLTextAreaElement>("[data-ds9-input]");
  if (ds8Input) ds8Input.value = (ds8.dynamic_ids || []).join("\n");
  if (ds9Input) ds9Input.value = (ds9.tags || []).join("\n");
  const ds8Count = wrap.querySelector<HTMLElement>("[data-ds8-count]");
  const ds9Count = wrap.querySelector<HTMLElement>("[data-ds9-count]");
  if (ds8Count) ds8Count.textContent = `${Number(ds8.count ?? ds8.dynamic_ids?.length ?? 0)} 条`;
  if (ds9Count) ds9Count.textContent = `${Number(ds9.count ?? ds9.tags?.length ?? 0)} 个话题`;
  renderDs10(data.ds10 || {});
  disableMutations(document.body.classList.contains("job-running"));
  bindActionButtons();
}

export async function loadDataSourceSettings(): Promise<SourceSettingsPayload | null> {
  const wrap = panel();
  if (!wrap) return null;
  const seq = ++sourceSettingsLoadSeq;
  try {
    const data = await fetchJSON<SourceSettingsPayload>("/api/source-settings");
    if (seq !== sourceSettingsLoadSeq) return data;
    render(data);
    setFeedback("");
    return data;
  } catch (error) {
    if (seq !== sourceSettingsLoadSeq) return null;
    disableMutations(true);
    setFeedback(`数据源配置加载失败，保存已禁用：${error instanceof Error ? error.message : String(error)}`, "error");
    return null;
  }
}

async function saveDs8(button: HTMLButtonElement): Promise<void> {
  const input = panel()?.querySelector<HTMLTextAreaElement>("[data-ds8-input]");
  button.disabled = true;
  try {
    await fetchJSON("/api/source-settings/ds8", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dynamic_ids: lineValues(input?.value || "") }),
    });
    await loadDataSourceSettings();
    showToast("DS-8 配置已保存", "success");
  } catch (error) {
    setFeedback(error instanceof Error ? error.message : String(error), "error");
  } finally {
    button.disabled = document.body.classList.contains("job-running");
  }
}

async function saveDs9(button: HTMLButtonElement): Promise<void> {
  const input = panel()?.querySelector<HTMLTextAreaElement>("[data-ds9-input]");
  button.disabled = true;
  try {
    await fetchJSON("/api/source-settings/ds9", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tags: lineValues(input?.value || "") }),
    });
    await loadDataSourceSettings();
    showToast("DS-9 配置已保存", "success");
  } catch (error) {
    setFeedback(error instanceof Error ? error.message : String(error), "error");
  } finally {
    button.disabled = document.body.classList.contains("job-running");
  }
}

async function addDs10(button: HTMLButtonElement): Promise<void> {
  const input = panel()?.querySelector<HTMLInputElement>("[data-ds10-input]");
  const source = String(input?.value || "").trim();
  if (!source) {
    setFeedback("请输入 DS-10 外部源 URL。", "error");
    input?.focus();
    return;
  }
  button.disabled = true;
  try {
    await fetchJSON("/api/source-settings/ds10", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source }),
    });
    if (input) input.value = "";
    await loadDataSourceSettings();
    showToast("DS-10 外部源已添加", "success");
  } catch (error) {
    setFeedback(error instanceof Error ? error.message : String(error), "error");
  } finally {
    button.disabled = document.body.classList.contains("job-running");
  }
}

async function removeDs10(button: HTMLButtonElement): Promise<void> {
  const sourceId = button.dataset.sourceEntryId;
  if (!sourceId) return;
  const row = button.closest(".managed-source-entry");
  const display = row?.querySelector("code")?.textContent || "该外部源";
  const confirmed = await openAppConfirm({
    eyebrow: "DS-10",
    title: "删除这个外部源？",
    desc: display,
    confirmLabel: "删除外部源",
    danger: true,
  });
  if (!confirmed) return;
  button.disabled = true;
  try {
    await fetchJSON(`/api/source-settings/ds10/${encodeURIComponent(sourceId)}`, { method: "DELETE" });
    await loadDataSourceSettings();
    showToast("DS-10 外部源已删除", "success");
  } catch (error) {
    setFeedback(error instanceof Error ? error.message : String(error), "error");
  } finally {
    button.disabled = document.body.classList.contains("job-running");
  }
}

function bindPanel(): void {
  const wrap = panel();
  if (!wrap || wrap.dataset.bound === "true") return;
  wrap.dataset.bound = "true";
  wrap.addEventListener("click", (event) => {
    const button = (event.target as Element).closest<HTMLButtonElement>("[data-source-setting-action]");
    if (!button || button.disabled || document.body.classList.contains("job-running")) return;
    const action = button.dataset.sourceSettingAction;
    if (action === "save-ds8") void saveDs8(button);
    else if (action === "save-ds9") void saveDs9(button);
    else if (action === "add-ds10") void addDs10(button);
    else if (action === "remove-ds10") void removeDs10(button);
  });
}

export function mountDataSourceSettings(): void {
  if (!sourceGrid || panel()) return;
  const wrap = buildPanel();
  sourceGrid.after(wrap);
  bindPanel();
  bindActionButtons();
  void loadDataSourceSettings();
}
