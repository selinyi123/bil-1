// 新功能前端面板：账号池 / 参与增强配置 / 通知配置 / 任务工具（中奖深检、清理）/ 运行日志
import { fetchJSON } from "../api/client";
import { loadActivities, loadSummary } from "../activities/index";
import { loadAccount } from "../account/index";
import { accountHero } from "../dom";
import { startJob } from "../jobs/index";
import { openAppConfirm as rawOpenAppConfirm } from "../shell/confirm";
import { showToast } from "../shell/toast";
import { escapeHtml } from "../utils/text";
import { loadWatchUsers } from "../watch/index";
import { mergeConfig, parseAtUsers, resolveCleanupPartitionName, type ConfigRecord } from "./config";

type AppConfirmOptions = {
  eyebrow?: string;
  title?: string;
  desc?: string;
  bullets?: string[];
  confirmLabel?: string;
  cancelLabel?: string;
  secondaryLabel?: string;
  danger?: boolean;
  onSecondary?: (() => void) | null;
};

/** openAppConfirm 来自 @ts-nocheck 模块，签名推导不完整（bullets 被推成 never[]），这里显式收窄。 */
const openAppConfirm = rawOpenAppConfirm as (options?: AppConfirmOptions) => Promise<boolean>;

let lastEnhanceConfig: ConfigRecord | null = null;
let lastNotifyConfig: ConfigRecord | null = null;

function errText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/**
 * 按钮 loading 辅助。设置、账号切换、破坏性任务默认禁止在 Job 运行中执行，
 * 避免同一任务中途切换账号/参与策略。日志查看可显式 allowDuringJob。
 */
async function withBusy<T>(
  btn: HTMLButtonElement | null,
  fn: () => Promise<T>,
  { allowDuringJob = false }: { allowDuringJob?: boolean } = {},
): Promise<T | undefined> {
  if (!btn || btn.disabled) return undefined;
  if (!allowDuringJob && document.body.classList.contains("job-running")) {
    showToast("有任务正在运行", "info", "请等待当前任务结束后再修改账号、配置或启动新任务");
    return undefined;
  }
  btn.disabled = true;
  try {
    return await fn();
  } finally {
    // 任务运行中保持全局锁定，不恢复危险按钮；日志按钮例外。
    btn.disabled = allowDuringJob ? false : document.body.classList.contains("job-running");
  }
}

function asInt(value: unknown): number | null {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

async function refreshAccountScopedViews(): Promise<void> {
  await loadAccount();
  // summary / activities / triple_targets 都带当前 uid 语义，切号后必须一起换上下文。
  await Promise.all([loadSummary(), loadActivities()]);
  await Promise.allSettled([loadWatchUsers()]);
  await renderAccountPool();
}

// ---------------------------------------------------------------------------
// 账号池面板（挂在账号 hero 下方）
// ---------------------------------------------------------------------------

export async function renderAccountPool(): Promise<void> {
  let panel = document.getElementById("account-pool-panel");
  if (!panel) {
    panel = document.createElement("div");
    panel.id = "account-pool-panel";
    panel.className = "panel account-pool";
    accountHero?.after(panel);
  }
  let data: { accounts?: Array<{ uid: number; active: boolean }>; active_uid?: number | null };
  try {
    data = await fetchJSON<{
      accounts: Array<{ uid: number; active: boolean }>;
      active_uid: number | null;
    }>("/api/accounts", { timeoutMs: 10000 });
  } catch {
    return; // 兼容老版本后端无此 API
  }
  const accounts = data.accounts || [];
  if (accounts.length <= 1) {
    panel.hidden = true;
    return;
  }
  panel.hidden = false;
  panel.innerHTML = `
    <div class="settings-panel-head">
      <div class="settings-panel-intro">
        <h2 class="section-title">账号池</h2>
        <p class="section-desc">多账号切换（参与记录按账号隔离）；切换后统计、活动状态与三连候选会同步切换。任务运行中不允许切换或删除。</p>
      </div>
    </div>
    <div class="account-pool-list">
      ${accounts
        .map(
          (acc) => `
        <div class="account-pool-item ${acc.active ? "is-active" : ""}" data-uid="${escapeHtml(String(acc.uid))}">
          <span class="account-pool-uid">UID ${escapeHtml(String(acc.uid))}</span>
          ${acc.active ? '<span class="account-pool-badge">当前</span>' : ""}
          <span class="account-pool-actions">
            ${acc.active ? "" : '<button type="button" class="btn btn-secondary btn-compact btn-pill" data-pool-switch="' + escapeHtml(String(acc.uid)) + '">切换</button>'}
            <button type="button" class="btn btn-ghost btn-compact btn-pill" data-pool-remove="${escapeHtml(String(acc.uid))}">删除</button>
          </span>
        </div>`,
        )
        .join("")}
    </div>`;

  panel.querySelectorAll<HTMLButtonElement>("[data-pool-switch]").forEach((btn) => {
    btn.addEventListener("click", () => {
      void withBusy(btn, async () => {
        const uid = Number(btn.dataset.poolSwitch);
        try {
          await fetchJSON("/api/accounts/switch", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ uid }),
          });
          try {
            await refreshAccountScopedViews();
            showToast("已切换账号", "success", `UID ${uid}`);
          } catch (refreshError) {
            showToast("账号已切换，但部分页面刷新失败", "warning", errText(refreshError));
            await renderAccountPool().catch(() => {});
          }
        } catch (error) {
          showToast(errText(error), "error");
        }
      });
    });
  });

  panel.querySelectorAll<HTMLButtonElement>("[data-pool-remove]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const uid = btn.dataset.poolRemove;
      if (!uid) return;
      void withBusy(btn, async () => {
        const confirmed = await openAppConfirm({
          eyebrow: "账号池",
          title: `确认删除账号 UID ${uid}？`,
          desc: "删除后该账号的 Cookie 与账号级网络配置会从本机移除；参与历史仍保留在数据库中。若删除当前账号，页面会立即切换到未登录状态。",
          confirmLabel: "删除账号",
          danger: true,
        });
        if (!confirmed) return;
        try {
          await fetchJSON(`/api/accounts/${uid}`, { method: "DELETE" });
          try {
            await refreshAccountScopedViews();
            showToast("账号已删除", "success");
          } catch (refreshError) {
            showToast("账号已删除，但部分页面刷新失败", "warning", errText(refreshError));
            await renderAccountPool().catch(() => {});
          }
        } catch (error) {
          showToast(errText(error), "error");
        }
      });
    });
  });
}

// ---------------------------------------------------------------------------
// 参与增强配置：常用字段表单 + 高级 JSON 切换
// ---------------------------------------------------------------------------

function buildEnhancePanel(): HTMLDivElement {
  const wrap = document.createElement("div");
  wrap.className = "panel extra-config-panel";
  wrap.id = "extra-panel-enhance";
  wrap.innerHTML = `
    <div class="settings-panel-head">
      <div class="settings-panel-intro">
        <h2 class="section-title">参与增强配置</h2>
        <p class="section-desc">随机评论过滤 / @好友 / 带话题 / 乱序 / 随机延迟 / 关注分区。是否随机借用评论由上方「参与文案」模式统一控制。</p>
      </div>
    </div>
    <div class="extra-mode-tabs" style="padding: 0 20px;">
      <button type="button" class="extra-mode-tab is-active" data-enhance-mode="form">常用设置</button>
      <button type="button" class="extra-mode-tab" data-enhance-mode="json">高级 JSON</button>
    </div>
    <div class="extra-form-section" data-enhance-form>
      <div class="extra-form-grid">
        <label class="extra-form-check"><input type="checkbox" id="enh-copy-chat-exclude"> 随机评论时排除活动作者</label>
        <label class="extra-form-check"><input type="checkbox" id="enh-shuffle"> 参与前乱序目标</label>
        <label class="extra-form-check"><input type="checkbox" id="enh-partition"> 参与后移入关注分区</label>
        <div class="extra-form-field">
          <label for="enh-topic">转发话题（可空）</label>
          <input type="text" id="enh-topic" placeholder="#每日抽奖#">
        </div>
        <div class="extra-form-field">
          <label for="enh-at-users">转发 @ 用户（每行 uid:昵称）</label>
          <textarea id="enh-at-users" spellcheck="false" placeholder="294887687:转发抽奖娘"></textarea>
        </div>
        <div class="extra-form-field">
          <label for="enh-blockwords">随机评论屏蔽词（逗号分隔）</label>
          <input type="text" id="enh-blockwords" placeholder="抽奖,互关">
        </div>
        <div class="extra-form-field">
          <label for="enh-interval-min">随机延迟下限（秒）</label>
          <input type="number" id="enh-interval-min" step="0.05" min="0">
        </div>
        <div class="extra-form-field">
          <label for="enh-interval-max">随机延迟上限（秒）</label>
          <input type="number" id="enh-interval-max" step="0.05" min="0">
        </div>
        <div class="extra-form-field">
          <label for="enh-partition-name">关注分区名称</label>
          <input type="text" id="enh-partition-name" placeholder="抽奖临时关注">
        </div>
      </div>
      <p class="extra-form-hint">@ 用户必须填写 <code>uid:昵称</code>；只填 UID 会被拒绝，避免保存后执行时静默失效。高级 JSON 中的 <code>copy_chat.enabled</code> 仅为旧配置兼容，不再是第二个运行期开关。</p>
    </div>
    <div class="extra-config-body" data-enhance-json hidden>
      <textarea class="extra-config-textarea" spellcheck="false" rows="14" placeholder="加载中…"></textarea>
    </div>
    <div class="settings-panel-foot" style="padding: 0 20px 20px; gap: 10px; flex-wrap: wrap;">
      <p class="extra-form-hint" data-extra-load-error hidden style="flex: 1 1 100%; margin: 0;"></p>
      <button type="button" class="btn btn-secondary btn-pill" data-extra-reload="enhance" hidden>重新加载</button>
      <button type="button" class="btn btn-primary btn-pill" data-extra-save="enhance">保存配置</button>
    </div>`;
  return wrap;
}

function readEnhanceForm(): ConfigRecord {
  const chk = (id: string) => (document.getElementById(id) as HTMLInputElement | null)?.checked ?? false;
  const val = (id: string) => (document.getElementById(id) as HTMLInputElement | null)?.value ?? "";
  const blockwords = val("enh-blockwords")
    .split(/[,，]/)
    .map((s) => s.trim())
    .filter(Boolean);
  const atUsers = parseAtUsers(val("enh-at-users"));
  const min = Number(val("enh-interval-min"));
  const max = Number(val("enh-interval-max"));
  return {
    // legacy compatibility only; participate_text_mode is the authoritative switch.
    copy_chat: {
      enabled: true,
      blockwords,
      exclude_author: chk("enh-copy-chat-exclude"),
    },
    at_users: atUsers,
    topic: val("enh-topic").trim(),
    shuffle_targets: chk("enh-shuffle"),
    action_interval_sec: {
      min: Number.isFinite(min) && min > 0 ? min : 0.75,
      max: Number.isFinite(max) && max > 0 ? max : 2.25,
    },
    partition: {
      enabled: chk("enh-partition"),
      name: val("enh-partition-name").trim() || "抽奖临时关注",
    },
  };
}

function fillEnhanceForm(config: ConfigRecord): void {
  const setChk = (id: string, value: unknown) => {
    const el = document.getElementById(id) as HTMLInputElement | null;
    if (el) el.checked = Boolean(value);
  };
  const setVal = (id: string, value: unknown) => {
    const el = document.getElementById(id) as HTMLInputElement | null;
    if (el) el.value = String(value ?? "");
  };
  const copyChat = (config.copy_chat ?? {}) as ConfigRecord;
  const interval = (config.action_interval_sec ?? {}) as ConfigRecord;
  const partition = (config.partition ?? {}) as ConfigRecord;
  const atUsers = (config.at_users ?? []) as Array<{ uid: number; name?: string }>;
  setChk("enh-copy-chat-exclude", copyChat.exclude_author);
  setChk("enh-shuffle", config.shuffle_targets);
  setChk("enh-partition", partition.enabled);
  setVal("enh-topic", config.topic);
  setVal(
    "enh-at-users",
    atUsers.filter((u) => u?.uid && u?.name).map((u) => `${u.uid}:${u.name}`).join("\n"),
  );
  setVal("enh-blockwords", ((copyChat.blockwords ?? []) as string[]).join(", "));
  setVal("enh-interval-min", interval.min ?? 0.75);
  setVal("enh-interval-max", interval.max ?? 2.25);
  setVal("enh-partition-name", partition.name ?? "抽奖临时关注");
}

// ---------------------------------------------------------------------------
// 通知配置：总开关 + 中奖关键词 + 渠道凭据表单 + 高级 JSON 切换
// ---------------------------------------------------------------------------

const CHANNEL_SCHEMA: Array<{
  key: string;
  label: string;
  fields: Array<{ key: string; label: string; secret?: boolean; type?: "number" }>;
}> = [
  { key: "serverchan", label: "Server酱(旧)", fields: [{ key: "sckey", label: "SCKEY", secret: true }] },
  { key: "sct", label: "Server酱³", fields: [{ key: "sendkey", label: "SendKey", secret: true }] },
  { key: "coolpush", label: "酷推", fields: [{ key: "key", label: "Key", secret: true }, { key: "mode", label: "Mode" }] },
  { key: "bark", label: "Bark", fields: [{ key: "push", label: "Push Key", secret: true }, { key: "sound", label: "铃声" }] },
  { key: "pushdeer", label: "PushDeer", fields: [{ key: "url", label: "Server URL" }, { key: "pushkey", label: "PushKey", secret: true }] },
  { key: "telegram", label: "Telegram", fields: [{ key: "bot_token", label: "Bot Token", secret: true }, { key: "chat_id", label: "Chat ID" }] },
  { key: "dingtalk", label: "钉钉", fields: [{ key: "token", label: "Token", secret: true }, { key: "secret", label: "加签密钥", secret: true }] },
  { key: "qywx_app", label: "企业微信(应用)", fields: [{ key: "corpid", label: "CorpID" }, { key: "secret", label: "Secret", secret: true }, { key: "agentid", label: "AgentID" }, { key: "touser", label: "接收人" }] },
  { key: "qywx_bot", label: "企业微信(机器人)", fields: [{ key: "key", label: "Webhook Key", secret: true }] },
  { key: "igot", label: "iGot", fields: [{ key: "key", label: "Key", secret: true }] },
  { key: "pushplus", label: "PushPlus", fields: [{ key: "token", label: "Token", secret: true }, { key: "topic", label: "群组编码" }] },
  { key: "qmsg", label: "Qmsg", fields: [{ key: "key", label: "Key", secret: true }, { key: "qq", label: "QQ" }, { key: "socket", label: "Socket" }] },
  { key: "email", label: "邮件", fields: [{ key: "host", label: "SMTP 主机" }, { key: "port", label: "端口", type: "number" }, { key: "user", label: "用户名" }, { key: "pass", label: "密码", secret: true }, { key: "to", label: "收件人" }] },
  { key: "gotify", label: "Gotify", fields: [{ key: "url", label: "Server URL" }, { key: "appkey", label: "AppKey", secret: true }] },
  { key: "feishu", label: "飞书", fields: [{ key: "webhook", label: "Webhook" }, { key: "secret", label: "加签密钥", secret: true }] },
];

function buildNotifyPanel(): HTMLDivElement {
  const wrap = document.createElement("div");
  wrap.className = "panel extra-config-panel";
  wrap.id = "extra-panel-notify";
  const channelsHtml = CHANNEL_SCHEMA.map(
    (ch) => `
    <div class="extra-form-field" data-notify-channel="${ch.key}">
      <label>${escapeHtml(ch.label)}</label>
      ${ch.fields
        .map((f) => {
          const inputType = f.type === "number" ? "number" : f.secret ? "password" : "text";
          const autocomplete = f.secret ? ' autocomplete="new-password"' : ' autocomplete="off"';
          return `<input type="${inputType}" data-channel-field="${f.key}" placeholder="${escapeHtml(f.label)}" aria-label="${escapeHtml(f.label)}（${escapeHtml(ch.label)}）"${autocomplete} ${f.secret ? 'data-secret="1"' : ""}>`;
        })
        .join("")}
    </div>`,
  ).join("");
  wrap.innerHTML = `
    <div class="settings-panel-head">
      <div class="settings-panel-intro">
        <h2 class="section-title">通知推送配置</h2>
        <p class="section-desc">中奖深检命中关键词后推送。已保存凭据只回显 ****，凭据输入框默认隐藏内容；主动清空后保存才会清除。</p>
      </div>
    </div>
    <div class="extra-mode-tabs" style="padding: 0 20px;">
      <button type="button" class="extra-mode-tab is-active" data-notify-mode="form">渠道设置</button>
      <button type="button" class="extra-mode-tab" data-notify-mode="json">高级 JSON</button>
    </div>
    <div class="extra-form-section" data-notify-form>
      <label class="extra-form-check"><input type="checkbox" id="notify-enabled"> 启用通知推送</label>
      <div class="extra-form-field">
        <label for="notify-keywords">中奖关键词（每行一条，支持 | 分隔）</label>
        <textarea id="notify-keywords" spellcheck="false" rows="4" placeholder="中奖|恭喜|获得|幸运|抽中|奖品|填写地址"></textarea>
      </div>
      <hr class="extra-form-divider">
      <div class="extra-form-grid">${channelsHtml}</div>
      <p class="extra-form-hint">任选渠道填写即可，未填写的渠道自动跳过；全部为空则仅记录不推送。表单保存会保留当前前端不认识的后端新字段。</p>
    </div>
    <div class="extra-config-body" data-notify-json hidden>
      <textarea class="extra-config-textarea" spellcheck="false" rows="14" placeholder="加载中…"></textarea>
    </div>
    <div class="settings-panel-foot" style="padding: 0 20px 20px; gap: 10px; flex-wrap: wrap;">
      <p class="extra-form-hint" data-extra-load-error hidden style="flex: 1 1 100%; margin: 0;"></p>
      <button type="button" class="btn btn-secondary btn-pill" data-extra-reload="notify" hidden>重新加载</button>
      <button type="button" class="btn btn-primary btn-pill" data-extra-save="notify">保存配置</button>
    </div>`;
  return wrap;
}

function readNotifyForm(): ConfigRecord {
  const enabled = (document.getElementById("notify-enabled") as HTMLInputElement | null)?.checked ?? true;
  const keywords = (document.getElementById("notify-keywords") as HTMLTextAreaElement | null)
    ?.value.split("\n")
    .map((s) => s.trim())
    .filter(Boolean) ?? [];
  const channels: ConfigRecord = {};
  document.querySelectorAll<HTMLDivElement>("[data-notify-channel]").forEach((card) => {
    const key = card.dataset.notifyChannel;
    if (!key) return;
    const fields: ConfigRecord = {};
    card.querySelectorAll<HTMLInputElement>("[data-channel-field]").forEach((input) => {
      const field = input.dataset.channelField;
      if (!field) return;
      const value = input.type === "number" ? asInt(input.value) : input.value.trim();
      fields[field] = value ?? "";
    });
    channels[key] = fields;
  });
  return { enabled, keywords, channels };
}

function fillNotifyForm(config: ConfigRecord): void {
  const enabledEl = document.getElementById("notify-enabled") as HTMLInputElement | null;
  if (enabledEl) enabledEl.checked = config.enabled !== false;
  const keywordsEl = document.getElementById("notify-keywords") as HTMLTextAreaElement | null;
  if (keywordsEl && Array.isArray(config.keywords)) keywordsEl.value = (config.keywords as string[]).join("\n");
  const channels = (config.channels ?? {}) as Record<string, ConfigRecord>;
  CHANNEL_SCHEMA.forEach((ch) => {
    const card = document.querySelector<HTMLDivElement>(`[data-notify-channel="${ch.key}"]`);
    const values = channels[ch.key] ?? {};
    card?.querySelectorAll<HTMLInputElement>("[data-channel-field]").forEach((input) => {
      const field = input.dataset.channelField;
      if (!field) return;
      const value = values[field];
      input.value = value === undefined || value === null ? "" : String(value);
    });
  });
}

function setConfigLoadState(
  wrap: HTMLDivElement,
  saveBtn: HTMLButtonElement,
  reloadBtn: HTMLButtonElement,
  error: unknown | null,
): void {
  const errorEl = wrap.querySelector<HTMLElement>("[data-extra-load-error]");
  if (error) {
    saveBtn.disabled = true;
    reloadBtn.hidden = false;
    if (errorEl) {
      errorEl.hidden = false;
      errorEl.textContent = `配置加载失败：${errText(error)}。为防止覆盖本机已有配置，保存已禁用。`;
    }
  } else {
    saveBtn.disabled = false;
    reloadBtn.hidden = true;
    if (errorEl) {
      errorEl.hidden = true;
      errorEl.textContent = "";
    }
  }
}

async function fetchConfig(api: string): Promise<ConfigRecord> {
  const data = await fetchJSON<{ config: unknown }>(api, { timeoutMs: 10000 });
  return (data.config ?? {}) as ConfigRecord;
}

// ---------------------------------------------------------------------------
// 面板装配
// ---------------------------------------------------------------------------

export async function mountExtraPanels(): Promise<void> {
  const anchor = document.querySelector<HTMLElement>(".participate-settings");
  if (!anchor) return;
  if (document.getElementById("extra-config-panels")) return; // 幂等

  const container = document.createElement("div");
  container.id = "extra-config-panels";
  container.style.display = "contents";
  anchor.after(container);

  const enhanceWrap = buildEnhancePanel();
  const notifyWrap = buildNotifyPanel();
  const tools = buildToolsPanel();
  const logs = buildLogsPanel();
  container.append(enhanceWrap, notifyWrap, tools, logs);

  bindEnhancePanel(enhanceWrap);
  bindNotifyPanel(notifyWrap);
  bindToolsPanel(tools);
  bindLogsPanel(logs);
}

// ---------------------------------------------------------------------------
// 参与增强面板绑定
// ---------------------------------------------------------------------------

function bindEnhancePanel(wrap: HTMLDivElement): void {
  const textarea = wrap.querySelector<HTMLTextAreaElement>("[data-enhance-json] textarea")!;
  const formSection = wrap.querySelector<HTMLElement>("[data-enhance-form]")!;
  const jsonSection = wrap.querySelector<HTMLElement>("[data-enhance-json]")!;
  const saveBtn = wrap.querySelector<HTMLButtonElement>("[data-extra-save='enhance']")!;
  const reloadBtn = wrap.querySelector<HTMLButtonElement>("[data-extra-reload='enhance']")!;
  let mode: "form" | "json" = "form";

  const load = async () => {
    saveBtn.disabled = true;
    reloadBtn.disabled = true;
    try {
      const config = await fetchConfig("/api/settings/enhance");
      lastEnhanceConfig = config;
      textarea.value = JSON.stringify(config, null, 2);
      fillEnhanceForm(config);
      syncCleanupPartitionLabel();
      setConfigLoadState(wrap, saveBtn, reloadBtn, null);
    } catch (error) {
      setConfigLoadState(wrap, saveBtn, reloadBtn, error);
    } finally {
      reloadBtn.disabled = false;
    }
  };

  wrap.querySelectorAll<HTMLButtonElement>("[data-enhance-mode]").forEach((tab) => {
    tab.addEventListener("click", () => {
      mode = tab.dataset.enhanceMode as "form" | "json";
      wrap.querySelectorAll("[data-enhance-mode]").forEach((t) => t.classList.toggle("is-active", t === tab));
      if (mode === "json") {
        if (lastEnhanceConfig) {
          textarea.value = JSON.stringify(mergeConfig(lastEnhanceConfig, readEnhanceForm()), null, 2);
        }
        formSection.hidden = true;
        jsonSection.hidden = false;
      } else {
        try {
          fillEnhanceForm(JSON.parse(textarea.value || "{}"));
        } catch {
          /* 保留当前表单值 */
        }
        jsonSection.hidden = true;
        formSection.hidden = false;
      }
    });
  });

  saveBtn.addEventListener("click", () => {
    void withBusy(saveBtn, async () => {
      if (!lastEnhanceConfig) {
        showToast("参与增强配置尚未成功加载", "error", "请先重新加载，避免覆盖已有配置");
        return;
      }
      try {
        const payload = mode === "form"
          ? mergeConfig(lastEnhanceConfig, readEnhanceForm())
          : JSON.parse(textarea.value || "{}");
        const response = await fetchJSON<{ config?: ConfigRecord }>("/api/settings/enhance", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        lastEnhanceConfig = (response.config ?? payload) as ConfigRecord;
        textarea.value = JSON.stringify(lastEnhanceConfig, null, 2);
        fillEnhanceForm(lastEnhanceConfig);
        syncCleanupPartitionLabel();
        showToast("参与增强配置已保存", "success");
      } catch (error) {
        showToast(errText(error), "error");
      }
    });
  });

  reloadBtn.addEventListener("click", () => {
    void withBusy(reloadBtn, load);
  });

  void load();
}

// ---------------------------------------------------------------------------
// 通知面板绑定
// ---------------------------------------------------------------------------

function bindNotifyPanel(wrap: HTMLDivElement): void {
  const textarea = wrap.querySelector<HTMLTextAreaElement>("[data-notify-json] textarea")!;
  const formSection = wrap.querySelector<HTMLElement>("[data-notify-form]")!;
  const jsonSection = wrap.querySelector<HTMLElement>("[data-notify-json]")!;
  const saveBtn = wrap.querySelector<HTMLButtonElement>("[data-extra-save='notify']")!;
  const reloadBtn = wrap.querySelector<HTMLButtonElement>("[data-extra-reload='notify']")!;
  let mode: "form" | "json" = "form";

  const load = async () => {
    saveBtn.disabled = true;
    reloadBtn.disabled = true;
    try {
      const config = await fetchConfig("/api/settings/notify");
      lastNotifyConfig = config;
      textarea.value = JSON.stringify(config, null, 2);
      fillNotifyForm(config);
      setConfigLoadState(wrap, saveBtn, reloadBtn, null);
    } catch (error) {
      setConfigLoadState(wrap, saveBtn, reloadBtn, error);
    } finally {
      reloadBtn.disabled = false;
    }
  };

  wrap.querySelectorAll<HTMLButtonElement>("[data-notify-mode]").forEach((tab) => {
    tab.addEventListener("click", () => {
      mode = tab.dataset.notifyMode as "form" | "json";
      wrap.querySelectorAll("[data-notify-mode]").forEach((t) => t.classList.toggle("is-active", t === tab));
      if (mode === "json") {
        if (lastNotifyConfig) {
          textarea.value = JSON.stringify(mergeConfig(lastNotifyConfig, readNotifyForm()), null, 2);
        }
        formSection.hidden = true;
        jsonSection.hidden = false;
      } else {
        try {
          fillNotifyForm(JSON.parse(textarea.value || "{}"));
        } catch {
          /* 保留当前表单值 */
        }
        jsonSection.hidden = true;
        formSection.hidden = false;
      }
    });
  });

  saveBtn.addEventListener("click", () => {
    void withBusy(saveBtn, async () => {
      if (!lastNotifyConfig) {
        showToast("通知配置尚未成功加载", "error", "请先重新加载，避免覆盖已有密钥");
        return;
      }
      try {
        const payload = mode === "form"
          ? mergeConfig(lastNotifyConfig, readNotifyForm())
          : JSON.parse(textarea.value || "{}");
        const response = await fetchJSON<{ config?: ConfigRecord }>("/api/settings/notify", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        lastNotifyConfig = (response.config ?? payload) as ConfigRecord;
        textarea.value = JSON.stringify(lastNotifyConfig, null, 2);
        fillNotifyForm(lastNotifyConfig);
        showToast("通知配置已保存", "success");
      } catch (error) {
        showToast(errText(error), "error");
      }
    });
  });

  reloadBtn.addEventListener("click", () => {
    void withBusy(reloadBtn, load);
  });

  void load();
}

// ---------------------------------------------------------------------------
// 任务工具面板（中奖深检 / 清理）
// ---------------------------------------------------------------------------

function buildToolsPanel(): HTMLDivElement {
  const tools = document.createElement("div");
  tools.className = "panel extra-tools-panel";
  tools.innerHTML = `
    <div class="settings-panel-head">
      <div class="settings-panel-intro">
        <h2 class="section-title">任务工具</h2>
        <p class="section-desc">中奖深检与清理工具。清理包含两个独立范围：超期转发删除，以及关注分区批量取关；时间阈值只影响动态删除。</p>
      </div>
    </div>
    <div class="extra-tools-body">
      <div class="extra-form-grid">
        <label class="extra-form-check"><input type="checkbox" id="check-prize-push" checked> 中奖深检命中后推送通知</label>
        <div class="extra-form-field">
          <label for="cleanup-max-days">转发动态超期阈值（天）</label>
          <input type="number" id="cleanup-max-days" min="1" max="365" step="1" value="30">
        </div>
        <label class="extra-form-check"><input type="checkbox" id="cleanup-delete-dynamic" checked> 删除 Binggo 确认归属的超期转发动态</label>
        <div class="extra-form-field">
          <label for="cleanup-partition-name">批量取关分区</label>
          <input type="text" id="cleanup-partition-name" value="抽奖临时关注" readonly>
        </div>
        <div class="extra-form-field">
          <label for="cleanup-whitelist">白名单 UID（逗号分隔）</label>
          <input type="text" id="cleanup-whitelist" inputmode="numeric" placeholder="123456,789012">
        </div>
      </div>
      <p class="extra-form-hint">分区取关与动态删除互相独立：即使关闭“删除动态”，清理仍会取关该分区内非白名单用户。建议先预演，并在任务日志中核对数量。</p>
      <div class="action-row">
        <button type="button" class="btn btn-secondary btn-pill" data-extra-tool="check_prize" title="扫描 @/回复/私信；是否推送由上方勾选项决定">中奖深检</button>
        <button type="button" class="btn btn-secondary btn-pill" data-extra-tool="clear_dry" title="预演清理，不真正删除或取关">清理（预演）</button>
        <button type="button" class="btn btn-ghost btn-pill" data-extra-tool="clear_run" title="按当前范围真实执行清理（有二次确认）">清理（执行）</button>
      </div>
    </div>`;
  return tools;
}

function syncCleanupPartitionLabel(): void {
  const input = document.getElementById("cleanup-partition-name") as HTMLInputElement | null;
  if (input) input.value = resolveCleanupPartitionName(lastEnhanceConfig);
}

function readCleanupParams(dryRun: boolean): Record<string, unknown> {
  const maxDaysInput = document.getElementById("cleanup-max-days") as HTMLInputElement | null;
  const maxDays = Number(maxDaysInput?.value || 30);
  if (!Number.isInteger(maxDays) || maxDays < 1 || maxDays > 365) {
    throw new Error("清理天数必须是 1～365 的整数");
  }
  const whitelistInput = document.getElementById("cleanup-whitelist") as HTMLInputElement | null;
  const rawWhitelist = String(whitelistInput?.value || "").trim();
  const whitelistParts = rawWhitelist
    ? rawWhitelist.split(/[,，\s]+/).map((item) => item.trim()).filter(Boolean)
    : [];
  if (whitelistParts.some((item) => !/^\d+$/.test(item) || Number(item) <= 0)) {
    throw new Error("白名单只能填写正整数 UID，并用逗号分隔");
  }
  return {
    dry_run: dryRun,
    max_days: maxDays,
    delete_dynamic: (document.getElementById("cleanup-delete-dynamic") as HTMLInputElement | null)?.checked ?? true,
    white_list: whitelistParts.join(","),
  };
}

function bindToolsPanel(tools: HTMLDivElement): void {
  syncCleanupPartitionLabel();
  tools.querySelectorAll<HTMLButtonElement>("[data-extra-tool]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tool = btn.dataset.extraTool;
      if (tool === "check_prize") {
        const push = (document.getElementById("check-prize-push") as HTMLInputElement | null)?.checked ?? true;
        void withBusy(btn, () => startJob("check_prize", { push }));
        return;
      }
      if (tool === "clear_dry") {
        void withBusy(btn, async () => {
          try {
            await startJob("clear_follows", readCleanupParams(true));
          } catch (error) {
            showToast(errText(error), "error");
          }
        });
        return;
      }
      if (tool !== "clear_run") return;

      void withBusy(btn, async () => {
        let params: Record<string, unknown>;
        try {
          params = readCleanupParams(false);
        } catch (error) {
          showToast(errText(error), "error");
          return;
        }
        const partition = resolveCleanupPartitionName(lastEnhanceConfig);
        const maxDays = Number(params.max_days || 30);
        const deleteDynamic = Boolean(params.delete_dynamic);
        const whitelist = String(params.white_list || "");
        const confirmed = await openAppConfirm({
          eyebrow: "清理 · 不可撤销",
          title: "确认执行真实清理？",
          desc: `${deleteDynamic ? `将删除超过 ${maxDays} 天、且由 Binggo 台账确认归属的转发动态；` : "本次不删除动态；"}另外会批量取关关注分区「${partition}」中的非白名单用户。两个范围互相独立。`,
          bullets: [
            "原创动态和无法确认由 Binggo 创建的转发动态不会删除",
            `分区「${partition}」内的非白名单用户会被批量取关，不按动态天数筛选`,
            whitelist ? `当前白名单：${whitelist}` : "当前未设置白名单",
            "建议先执行预演，并在任务日志核对预计删除与取关数量",
          ],
          confirmLabel: "确认真实清理",
          danger: true,
          secondaryLabel: "先执行预演",
          onSecondary: () => {
            tools.querySelector<HTMLButtonElement>("[data-extra-tool='clear_dry']")?.click();
          },
        });
        if (!confirmed) return;
        await startJob("clear_follows", params);
      });
    });
  });
}

// ---------------------------------------------------------------------------
// 运行日志面板
// ---------------------------------------------------------------------------

function buildLogsPanel(): HTMLDivElement {
  const logs = document.createElement("div");
  logs.className = "panel extra-logs-panel";
  logs.id = "extra-panel-logs";
  logs.innerHTML = `
    <div class="settings-panel-head">
      <div class="settings-panel-intro">
        <h2 class="section-title">运行日志</h2>
        <p class="section-desc">查看最近任务运行日志（支持按 job_id 过滤），便于排查失败原因。</p>
      </div>
    </div>
    <div class="extra-logs-body">
      <div class="extra-log-toolbar">
        <input type="number" id="extra-log-limit" min="10" max="500" value="50" title="最多显示行数" aria-label="日志显示行数">
        <input type="text" id="extra-log-job" placeholder="job_id（可选）" title="按任务 ID 过滤" aria-label="按任务 ID 过滤">
        <button type="button" class="btn btn-secondary btn-pill" data-extra-log="refresh">刷新日志</button>
        <span class="extra-log-meta" data-extra-log-meta></span>
      </div>
      <pre class="extra-log-output" data-extra-log-output hidden></pre>
      <p class="extra-log-empty" data-extra-log-empty>尚未加载日志，点击「刷新日志」。</p>
    </div>`;
  return logs;
}

function bindLogsPanel(logs: HTMLDivElement): void {
  const refreshBtn = logs.querySelector<HTMLButtonElement>("[data-extra-log='refresh']")!;
  const output = logs.querySelector<HTMLPreElement>("[data-extra-log-output]")!;
  const empty = logs.querySelector<HTMLElement>("[data-extra-log-empty]")!;
  const meta = logs.querySelector<HTMLElement>("[data-extra-log-meta]")!;
  refreshBtn.addEventListener("click", () => {
    void withBusy(
      refreshBtn,
      async () => {
        try {
          const limitEl = document.getElementById("extra-log-limit") as HTMLInputElement | null;
          const jobEl = document.getElementById("extra-log-job") as HTMLInputElement | null;
          const limit = Math.min(500, Math.max(10, Number(limitEl?.value) || 50));
          const jobRaw = (jobEl?.value ?? "").trim();
          const jobId = jobRaw ? asInt(jobRaw) : undefined;
          const params = new URLSearchParams({ limit: String(limit) });
          if (jobId !== undefined && jobId !== null) params.set("job_id", String(jobId));
          const data = await fetchJSON<{ count: number; lines?: string[]; files?: string[] }>(
            `/api/diagnostics/logs?${params.toString()}`,
            { timeoutMs: 15000 },
          );
          const lines = data.lines ?? [];
          if (lines.length === 0) {
            output.hidden = true;
            output.textContent = "";
            empty.hidden = false;
            empty.textContent = "没有匹配的日志行。";
            meta.textContent = "";
          } else {
            empty.hidden = true;
            output.hidden = false;
            output.textContent = lines.join("\n");
            meta.textContent = `共 ${data.count} 行（${lines.length} 行已显示）`;
          }
        } catch (error) {
          output.hidden = true;
          empty.hidden = false;
          empty.textContent = `日志加载失败：${errText(error)}`;
          meta.textContent = "";
        }
      },
      { allowDuringJob: true },
    );
  });
}
