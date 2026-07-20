import { expect, type APIRequestContext, type Page } from "@playwright/test";

export type E2EAccount = "logged_out" | "logged_in";
export type E2ELlm = "not_ready" | "ready";

export async function setE2EState(
  request: APIRequestContext,
  state: { account?: E2EAccount; llm?: E2ELlm },
): Promise<void> {
  const response = await request.post("/api/testing/e2e-state", { data: state });
  expect(response.ok(), `e2e-state failed: ${response.status()}`).toBeTruthy();
  const body = await response.json();
  expect(body.ok).toBeTruthy();
}

export async function gotoOverview(page: Page): Promise<void> {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "概览" })).toBeVisible({ timeout: 15_000 });
}

/** 在导航前注册，避免 SSE 已连上导致 waitForResponse 空等超时。 */
export function waitForSseConnect(page: Page, timeoutMs = 20_000) {
  return page.waitForResponse(
    (res) => res.url().includes("/api/events") && res.status() === 200,
    { timeout: timeoutMs },
  );
}

export async function openActivities(page: Page): Promise<void> {
  await page.locator('[data-section="activities"]').click();
  await expect(page.getByRole("heading", { name: "活动" })).toBeVisible({ timeout: 10_000 });
}

export async function confirmModal(page: Page): Promise<void> {
  const modal = page.locator("#app-confirm-modal");
  await expect(modal).toBeVisible({ timeout: 5_000 });
  await page.locator("#app-confirm-yes").click();
}
