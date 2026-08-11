import { expect, test } from "@playwright/test";
import { gotoOverview, setE2EState } from "./helpers";

test.describe("Frontend contract safety", () => {
  test("notify config GET failure disables save instead of treating it as empty config", async ({ page, request }) => {
    await setE2EState(request, { account: "logged_in", llm: "ready" });
    await page.route("**/api/settings/notify", async (route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({
            error: { code: "INTERNAL", message: "temporary config read failure", detail: null },
          }),
        });
        return;
      }
      await route.continue();
    });

    await gotoOverview(page);

    const save = page.locator("[data-extra-save='notify']");
    await expect(save).toBeVisible({ timeout: 10_000 });
    await expect(save).toBeDisabled();
    await expect(page.locator("#extra-panel-notify [data-extra-load-error]")).toContainText(
      "保存已禁用",
    );
    await expect(page.locator("[data-extra-reload='notify']")).toBeVisible();
  });

  test("notification credentials use password inputs", async ({ page, request }) => {
    await setE2EState(request, { account: "logged_in", llm: "ready" });
    await gotoOverview(page);

    const token = page.locator(
      "[data-notify-channel='telegram'] [data-channel-field='bot_token']",
    );
    await expect(token).toBeVisible({ timeout: 10_000 });
    await expect(token).toHaveAttribute("type", "password");
    await expect(token).toHaveAttribute("autocomplete", "new-password");
  });
});
