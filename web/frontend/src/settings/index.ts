// @ts-nocheck
/* eslint-disable */
/** Migrated from web/static/app.js — logic preserved. */

import { state } from "../state";
import { fetchJSON } from "../api/client";
import { isLoggedIn, renderAccountViews, renderOnboardingPanel } from "../account/index";
import { llmActionFeedback, participateTextFeedback } from "../dom";
import { setInlineFeedback, showToast } from "../shell/toast";
import { clearSaveDirty, flashButtonSuccess, markSaveDirty, prefersReducedMotion, setButtonLoading } from "../utils/motion";

export function toggleLlmApiKeyVisibility() {
  const input = document.getElementById("llm-api-key-input");
  const toggle = document.getElementById("llm-api-key-toggle");
  if (!input || !toggle) return;
  const showPlain = input.type === "password";
  input.type = showPlain ? "text" : "password";
  toggle.textContent = showPlain ? "隐藏" : "显示";
  toggle.setAttribute("aria-label", showPlain ? "隐藏 API Key" : "显示 API Key");
  toggle.setAttribute("aria-pressed", showPlain ? "true" : "false");
}

export function bindLlmApiKeyToggle() {
  const toggle = document.getElementById("llm-api-key-toggle");
  if (!toggle || toggle.dataset.bound === "true") return;
  toggle.dataset.bound = "true";
  toggle.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    toggleLlmApiKeyVisibility();
  });
}

export async function loadSettings() {
  const settings = await fetchJSON("/api/settings");
  state.settings = settings;
  renderParticipateSettings(settings);
  renderLlmSettingsForm(settings);
  return settings;
}

export function getParticipateTextDefaults(settings) {
  return {
    custom: settings?.default_participate_text || "好运连连！",
    fallback: settings?.default_participate_fallback_text || settings?.default_participate_text || "好运连连！",
  };
}

export function getParticipateTextForMode(settings, mode) {
  const defaults = getParticipateTextDefaults(settings || {});
  if (mode === "random_comment") {
    return settings?.participate_fallback_text || defaults.fallback;
  }
  return settings?.participate_text || defaults.custom;
}

export function updateParticipateTextUI(mode) {
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

export function renderParticipateSettings(settings) {
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

export async function saveParticipateTextMode(mode) {
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

export function bindParticipateSettings() {
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

export function bindSettingsDirtyTracking() {
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

export function getLlmFormValues() {
  return {
    api_key: document.getElementById("llm-api-key-input")?.value || "",
    base_url: document.getElementById("llm-base-url-input")?.value || "",
    model_name: document.getElementById("llm-model-name-input")?.value || "",
  };
}

export function renderLlmSettingsForm(settings) {
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

export async function refreshLlmSettings() {
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

export async function saveLlmSettings() {
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

export async function testLlmSettings() {
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

export async function saveParticipateText() {
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

export async function resetParticipateText() {
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
