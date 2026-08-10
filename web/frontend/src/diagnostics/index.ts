/* eslint-disable */

import { fetchJSON } from "../api/client";
import { state } from "../state";
import { showToast } from "../shell/toast";
import { setButtonLoading } from "../utils/motion";
import { sanitizeUserText } from "../utils/text";

function downloadTextFile(filename: string, text: string) {
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename || "binggo-diagnostics.txt";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export async function exportDiagnosticsBundle() {
  const button = document.getElementById("export-diagnostics") as HTMLButtonElement | null;
  setButtonLoading(button, true, { label: "导出中…" });
  try {
    const rawId = state.currentJob?.id;
    const jobId = Number.isFinite(Number(rawId)) && Number(rawId) > 0 ? Number(rawId) : null;
    const query = jobId ? `?job_id=${encodeURIComponent(String(jobId))}` : "";
    const result = await fetchJSON<Record<string, any>>(`/api/diagnostics/bundle${query}`, { timeoutMs: 30000 });
    const text = String(result?.text || "");
    const filename = String(result?.filename || "binggo-diagnostics.txt");
    if (!text) {
      throw new Error("诊断包为空");
    }
    let copied = false;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        copied = true;
      }
    } catch {
      copied = false;
    }
    downloadTextFile(filename, text);
    showToast(
      copied ? "诊断包已复制并下载" : "诊断包已下载",
      "success",
      copied ? "可直接粘贴到聊天或邮件" : "当前环境无法写入剪贴板，已保存文件",
    );
  } catch (error: any) {
    showToast(sanitizeUserText(error?.message || error) || "导出诊断包失败", "error");
  } finally {
    setButtonLoading(button, false);
  }
}

export function bindDiagnosticsExport() {
  document.getElementById("export-diagnostics")?.addEventListener("click", () => {
    exportDiagnosticsBundle().catch(() => {});
  });
}
