import { describe, expect, it } from "vitest";
import { parseApiErrorPayload } from "./client";

describe("parseApiErrorPayload", () => {
  it("reads error.code and error.message from contract payload", () => {
    const raw = JSON.stringify({
      error: { code: "AUTH_REQUIRED", message: "请先登录", detail: null },
      detail: "请先登录",
    });
    const parsed = parseApiErrorPayload(raw, "Unauthorized");
    expect(parsed.code).toBe("AUTH_REQUIRED");
    expect(parsed.message).toBe("请先登录");
  });

  it("falls back to top-level detail string", () => {
    const raw = JSON.stringify({ detail: "旧版错误文案" });
    const parsed = parseApiErrorPayload(raw, "Bad Request");
    expect(parsed.code).toBe("");
    expect(parsed.message).toBe("旧版错误文案");
  });

  it("maps detail array to generic validation message", () => {
    const raw = JSON.stringify({ detail: [{ loc: ["body"], msg: "field required" }] });
    const parsed = parseApiErrorPayload(raw, "Unprocessable Entity");
    expect(parsed.message).toBe("请求参数无效");
    expect(Array.isArray(parsed.detail)).toBe(true);
  });

  it("keeps non-JSON body as message", () => {
    const parsed = parseApiErrorPayload("<html>oops</html>", "Bad Gateway");
    expect(parsed.code).toBe("");
    expect(parsed.message).toContain("oops");
  });
});
