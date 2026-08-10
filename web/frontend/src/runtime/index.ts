/* eslint-disable */

import { fetchJSON } from "../api/client";
import { showToast } from "../shell/toast";
import { setButtonLoading } from "../utils/motion";
import { safeUrl, sanitizeUserText } from "../utils/text";

const RELEASES_URL = "https://github.com/luovicter-collab/bilibinggo/releases";

export async function loadRuntimeInfo() {
  const versionEl = document.getElementById("runtime-version");
  const runtimeEl = document.getElementById("runtime-label");
  const dataDirEl = document.getElementById("runtime-data-dir");
  const hintEl = document.getElementById("runtime-health-hint");
  if (!versionEl && !runtimeEl && !dataDirEl) {
    return;
  }
  try {
    const data = await fetchJSON<Record<string, any>>("/api/runtime", { timeoutMs: 8000 });
    const version = String(data?.version || "—");
    const runtime = String(data?.runtime || "—");
    const dataDir = String(data?.data_dir || "—");
    if (versionEl) {
      versionEl.textContent = version;
    }
    if (runtimeEl) {
      runtimeEl.textContent = runtime;
    }
    if (dataDirEl) {
      dataDirEl.textContent = dataDir;
      dataDirEl.title = dataDir;
    }
    const findings = Array.isArray(data?.findings) ? data.findings : [];
    const warnings = findings.filter((item) => item && item.severity === "warning");
    if (hintEl) {
      if (warnings.length) {
        const first = warnings[0];
        hintEl.hidden = false;
        hintEl.textContent = sanitizeUserText(first.message || "配置自检有提示") || "配置自检有提示";
      } else {
        hintEl.hidden = true;
        hintEl.textContent = "";
      }
    }
  } catch {
    // 静默：不影响主功能
  }
}

export function bindCheckUpdates() {
  const button = document.getElementById("check-updates") as HTMLButtonElement | null;
  if (!button || button.dataset.bound === "1") {
    return;
  }
  button.dataset.bound = "1";
  button.addEventListener("click", () => {
    checkForUpdates(button).catch(() => {});
  });
}

function openUpdateUrl(data: Record<string, any>) {
  const downloadUrl = String(data?.download_url || "").trim();
  const releaseUrl = String(data?.release_url || RELEASES_URL).trim() || RELEASES_URL;
  const target = safeUrl(downloadUrl) || safeUrl(releaseUrl);
  if (target) window.open(target, "_blank", "noopener");
}

async function checkForUpdates(button: HTMLButtonElement) {
  setButtonLoading(button, true, { label: "检查中…" });
  try {
    const data = await fetchJSON<Record<string, any>>("/api/updates/check", {
      method: "POST",
      timeoutMs: 12000,
    });
    const message = sanitizeUserText(data?.message) || "检查完成";
    const hint = sanitizeUserText(data?.hint) || "";
    const releaseUrl = String(data?.release_url || RELEASES_URL).trim() || RELEASES_URL;

    if (!data?.ok) {
      showToast(message, "error", hint, [
        {
          label: "打开 Releases",
          onClick: () => {
            const target = safeUrl(releaseUrl);
            if (target) window.open(target, "_blank", "noopener");
          },
        },
      ]);
      return;
    }

    if (data.update_available) {
      showToast(message, "info", hint || "可前往 Releases 下载对应平台安装包", [
        {
          label: "前往下载",
          onClick: () => openUpdateUrl(data),
        },
      ]);
      return;
    }

    showToast(message, "success", hint);
  } catch (error: any) {
    showToast(sanitizeUserText(error?.message || error) || "检查更新失败", "error");
  } finally {
    setButtonLoading(button, false);
  }
}
