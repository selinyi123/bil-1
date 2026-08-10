import type { ApiError } from "../types";

export type FetchJSONOptions = RequestInit & {
  timeoutMs?: number;
};

/** Parse API error payload (contract v1 dual-read). Exported for tests. */
export function parseApiErrorPayload(
  text: string,
  statusText: string,
): { message: string; code: string; detail: unknown } {  let message = text || statusText;
  let code = "";
  let detail: unknown = null;
  try {
    const payload = JSON.parse(text);
    const errObj = payload?.error;
    if (errObj && typeof errObj === "object") {
      if (errObj.message) message = String(errObj.message);
      code = String(errObj.code || "");
      detail = errObj.detail ?? null;
    } else if (typeof payload?.detail === "string") {
      message = payload.detail;
    } else if (Array.isArray(payload?.detail)) {
      message = "请求参数无效";
      detail = payload.detail;
    }
  } catch {
    // 非 JSON 响应，保留原始文本
  }
  return { message, code, detail };
}

let lastAuthExpiredAt = 0;

/** 401/403：广播登录失效事件（去抖 5s），由 account 层刷新登录态。 */
function notifyAuthExpired(status: number): void {
  const now = Date.now();
  if (now - lastAuthExpiredAt < 5000) return;
  lastAuthExpiredAt = now;
  window.dispatchEvent(
    new CustomEvent("binggo:auth-expired", { detail: { status } }),
  );
}

export async function fetchJSON<T = unknown>(
  url: string,
  options: FetchJSONOptions = {},
): Promise<T> {
  const { timeoutMs = 30000, ...fetchOptions } = options;
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      cache: "no-store",
      ...fetchOptions,
      signal: controller.signal,
    });
    if (!response.ok) {
      const text = await response.text();
      const { message, code, detail } = parseApiErrorPayload(text, response.statusText);
      const error = new Error(message) as ApiError;
      error.code = code;
      error.httpStatus = response.status;
      error.detail = detail;
      if (response.status === 401 || response.status === 403) {
        notifyAuthExpired(response.status);
      }
      throw error;
    }
    // 204 / 空 body：避免 response.json() 抛 SyntaxError
    if (response.status === 204) {
      return undefined as T;
    }
    const text = await response.text();
    if (!text) {
      return undefined as T;
    }
    return JSON.parse(text) as T;
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      throw new Error("请求超时，请稍后重试");
    }
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}
