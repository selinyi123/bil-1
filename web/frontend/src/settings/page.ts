import { fetchJSON } from "../api/client";
import { showToast } from "../shell/toast";
import { escapeHtml } from "../utils/text";

interface ProxySettingsPayload {
  ok?: boolean;
  uid?: number;
  editable?: boolean;
  effective_source?: "environment" | "account" | "global" | "none" | string;
  effective_proxy?: string | null;
  env_override?: boolean;
  account_configured?: boolean;
  account_proxy?: string | null;
  global_configured?: boolean;
  global_proxy?: string | null;
}

let proxyLoadSeq = 0;

function settingsSection(): HTMLElement | null {
  return document.getElementById("section-settings");
}

function sourceLabel(source: string | undefined): string {
  const labels: Record<string, string> = {
    environment: "环境变量 BINGGO_PROXY",
    account: "当前账号覆盖",
    global: "全局 proxy.json",
    none: "直连",
  };
  return labels[String(source || "none")] || String(source || "直连");
}

function buildSettingsNav(): HTMLButtonElement {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "nav-item";
  button.dataset.section = "settings";
  button.title = "设置";
  button.setAttribute("aria-label", "设置");
  button.innerHTML = `
    <span class="nav-icon" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
        <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.12 2.12-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.56V20.3h-3v-.08a1.7 1.7 0 0 0-1.03-1.56 1.7 1.7 0 0 0-1.88.34l-.06.06-2.12-2.12.06-.06A1.7 1.7 0 0 0 7 15a1.7 1.7 0 0 0-1.56-1.03H5.3v-3h.14A1.7 1.7 0 0 0 7 9.94a1.7 1.7 0 0 0-.34-1.88L6.6 8l2.12-2.12.06.06a1.7 1.7 0 0 0 1.88.34A1.7 1.7 0 0 0 11.7 4.7v-.1h3v.1a1.7 1.7 0 0 0 1.03 1.58 1.7 1.7 0 0 0 1.88-.34l.06-.06L19.8 8l-.06.06a1.7 1.7 0 0 0-.34 1.88 1.7 1.7 0 0 0 1.56 1.03h.14v3h-.14A1.7 1.7 0 0 0 19.4 15z"/>
      </svg>
    </span>
    <span class="nav-label sidebar-fade">设置</span>`;
  return button;
}

function buildProxyPanel(): HTMLElement {
  const panel = document.createElement("article");
  panel.className = "panel settings-network-panel";
  panel.id = "settings-proxy-panel";
  panel.innerHTML = `
    <div class="settings-panel-head">
      <div class="settings-panel-intro">
        <p class="eyebrow">Network</p>
        <h2 class="section-title">账号级 Proxy</h2>
        <p class="section-desc">仅覆盖当前账号。优先级固定为 BINGGO_PROXY → 当前账号 → 全局 proxy.json → 直连；已保存凭据只显示脱敏值。</p>
      </div>
    </div>
    <div class="settings-architecture-body">
      <div class="settings-state-grid" data-proxy-state>
        <div><span class="caption">当前账号</span><strong data-proxy-uid>—</strong></div>
        <div><span class="caption">实际生效</span><strong data-proxy-source>—</strong></div>
        <div><span class="caption">代理地址</span><strong class="mono-value" data-proxy-effective>—</strong></div>
      </div>
      <p class="settings-callout" data-proxy-notice hidden></p>
      <label class="settings-field settings-field-full">
        <span class="field-label">覆盖当前账号代理</span>
        <span class="field-help">输入完整 http:// 或 https:// 地址。留空不会覆盖；清除请使用独立按钮。</span>
        <input class="input" type="password" autocomplete="new-password" data-proxy-input placeholder="http://user:password@host:port">
      </label>
      <div class="settings-action-row">
        <button type="button" class="btn btn-primary btn-pill" data-settings-action="save-proxy">保存账号覆盖</button>
        <button type="button" class="btn btn-secondary btn-pill" data-settings-action="clear-proxy">清除账号覆盖</button>
      </div>
      <p class="inline-feedback" data-proxy-feedback hidden></p>
    </div>`;
  return panel;
}

function moveExistingSettings(section: HTMLElement): void {
  let stack = section.querySelector<HTMLElement>(".settings-architecture-stack");
  if (!stack) {
    stack = document.createElement("div");
    stack.className = "settings-architecture-stack";
    section.appendChild(stack);
  }
  const participate = document.querySelector<HTMLElement>(".participate-settings");
  const llm = document.getElementById("llm-settings-panel");
  if (participate && participate.parentElement !== stack) stack.appendChild(participate);
  if (llm && llm.parentElement !== stack) stack.appendChild(llm);
  if (!document.getElementById("settings-proxy-panel")) stack.appendChild(buildProxyPanel());
}

function bindProxyPanel(): void {
  const panel = document.getElementById("settings-proxy-panel");
  if (!panel || panel.dataset.bound === "true") return;
  panel.dataset.bound = "true";
  const input = panel.querySelector<HTMLInputElement>("[data-proxy-input]");
  const feedback = panel.querySelector<HTMLElement>("[data-proxy-feedback]");

  const setFeedback = (text: string, tone = "info") => {
    if (!feedback) return;
    feedback.hidden = !text;
    feedback.textContent = text;
    feedback.dataset.tone = tone;
  };

  panel.querySelector<HTMLButtonElement>("[data-settings-action='save-proxy']")?.addEventListener("click", async (event) => {
    const button = event.currentTarget as HTMLButtonElement;
    if (document.body.classList.contains("job-running")) return;
    const proxy = String(input?.value || "").trim();
    if (!proxy) {
      setFeedback("请输入代理地址；如果要恢复继承链，请点击“清除账号覆盖”。", "error");
      input?.focus();
      return;
    }
    button.disabled = true;
    try {
      await fetchJSON("/api/settings/proxy", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ proxy, clear: false }),
      });
      if (input) input.value = "";
      setFeedback("账号级代理已保存。", "success");
      await loadProxySettings();
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : String(error), "error");
    } finally {
      button.disabled = document.body.classList.contains("job-running");
    }
  });

  panel.querySelector<HTMLButtonElement>("[data-settings-action='clear-proxy']")?.addEventListener("click", async (event) => {
    const button = event.currentTarget as HTMLButtonElement;
    if (document.body.classList.contains("job-running")) return;
    button.disabled = true;
    try {
      await fetchJSON("/api/settings/proxy", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ clear: true }),
      });
      if (input) input.value = "";
      setFeedback("账号级代理已清除，已恢复上级继承。", "success");
      await loadProxySettings();
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : String(error), "error");
    } finally {
      button.disabled = document.body.classList.contains("job-running");
    }
  });
}

function renderProxySettings(data: ProxySettingsPayload): void {
  const panel = document.getElementById("settings-proxy-panel");
  if (!panel) return;
  panel.querySelector<HTMLElement>("[data-proxy-uid]")!.textContent = data.uid ? `UID ${data.uid}` : "—";
  panel.querySelector<HTMLElement>("[data-proxy-source]")!.textContent = sourceLabel(data.effective_source);
  panel.querySelector<HTMLElement>("[data-proxy-effective]")!.textContent = data.effective_proxy || "直连";
  const notice = panel.querySelector<HTMLElement>("[data-proxy-notice]");
  const clearBtn = panel.querySelector<HTMLButtonElement>("[data-settings-action='clear-proxy']");
  const saveBtn = panel.querySelector<HTMLButtonElement>("[data-settings-action='save-proxy']");
  const input = panel.querySelector<HTMLInputElement>("[data-proxy-input]");
  const editable = data.editable !== false;
  if (input) input.disabled = !editable;
  if (saveBtn) saveBtn.disabled = !editable || document.body.classList.contains("job-running");
  if (clearBtn) clearBtn.disabled = !editable || !data.account_configured || document.body.classList.contains("job-running");
  if (notice) {
    if (!editable) {
      notice.hidden = false;
      notice.textContent = "当前身份未登记到账号池，账号级 Proxy 只读。";
    } else if (data.env_override) {
      notice.hidden = false;
      notice.textContent = "BINGGO_PROXY 正在覆盖账号设置；这里保存的账号代理会保留，但当前不会生效。";
    } else if (data.account_configured) {
      notice.hidden = false;
      notice.textContent = `当前账号已配置覆盖：${data.account_proxy || "已配置"}`;
    } else if (data.global_configured) {
      notice.hidden = false;
      notice.textContent = `当前账号未覆盖，正在继承全局代理：${data.global_proxy || "已配置"}`;
    } else {
      notice.hidden = true;
      notice.textContent = "";
    }
  }
}

export async function loadProxySettings(): Promise<ProxySettingsPayload | null> {
  const panel = document.getElementById("settings-proxy-panel");
  if (!panel) return null;
  const seq = ++proxyLoadSeq;
  try {
    const data = await fetchJSON<ProxySettingsPayload>("/api/settings/proxy");
    if (seq !== proxyLoadSeq) return data;
    renderProxySettings(data);
    return data;
  } catch (error) {
    if (seq !== proxyLoadSeq) return null;
    const effective = panel.querySelector<HTMLElement>("[data-proxy-effective]");
    if (effective) effective.textContent = "加载失败";
    panel.querySelectorAll<HTMLButtonElement>("[data-settings-action]").forEach((button) => {
      button.disabled = true;
    });
    const notice = panel.querySelector<HTMLElement>("[data-proxy-notice]");
    if (notice) {
      notice.hidden = false;
      notice.textContent = `Proxy 配置加载失败，保存已禁用：${escapeHtml(error instanceof Error ? error.message : String(error))}`;
    }
    return null;
  }
}

/**
 * 正式 Settings 信息架构：在导航和内容区创建独立 Settings section，并把历史
 * Overview 中的参与文案 / LLM 面板迁入。Enhance / Notify 面板随后会以参与文案
 * 为 anchor 挂入同一 section，不再继续堆在 Overview。
 */
export function mountSettingsArchitecture(): void {
  const nav = document.querySelector<HTMLElement>(".sidebar-nav");
  if (nav && !nav.querySelector("[data-section='settings']")) nav.appendChild(buildSettingsNav());

  let section = settingsSection();
  if (!section) {
    section = document.createElement("section");
    section.className = "view-section";
    section.id = "section-settings";
    section.dataset.title = "设置";
    section.dataset.subtitle = "参与策略、LLM、通知与账号级网络配置。";
    document.querySelector(".content-area")?.appendChild(section);
  }
  moveExistingSettings(section);
  bindProxyPanel();
}
