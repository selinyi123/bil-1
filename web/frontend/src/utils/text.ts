/* eslint-disable */
/** Migrated from web/static/app.js — logic preserved. */


export function sanitizeUserText(text: unknown) {
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

export function escapeHtml(value: unknown) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;")
    .replace(/`/g, "&#96;");
}

/** 只允许 http/https 链接，其它协议（javascript: 等）返回空串。 */
export function safeUrl(value: unknown): string {
  const raw = String(value || "").trim();
  if (!raw) return "";
  try {
    const url = new URL(raw, window.location.href);
    return url.protocol === "http:" || url.protocol === "https:" ? url.href : "";
  } catch {
    return "";
  }
}

export function truncateText(text: unknown, maxLen = 28) {
  const value = String(text || "").trim();
  if (value.length <= maxLen) return value;
  return `${value.slice(0, maxLen - 1)}…`;
}
