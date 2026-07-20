// @ts-nocheck
/* eslint-disable */
/** Migrated from web/static/app.js — logic preserved. */


export function sanitizeUserText(text) {
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

export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

export function truncateText(text, maxLen = 28) {
  const value = String(text || "").trim();
  if (value.length <= maxLen) return value;
  return `${value.slice(0, maxLen - 1)}…`;
}
