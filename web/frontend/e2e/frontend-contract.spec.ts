import { expect, test } from "@playwright/test";
import { gotoOverview, setE2EState } from "./helpers";

async function openSettings(page: import("@playwright/test").Page) {
  await page.locator("[data-section='settings']").click();
  await expect(page.locator("#section-settings")).toHaveClass(/active/);
}

async function openSources(page: import("@playwright/test").Page) {
  await page.locator("[data-section='sources']").click();
  await expect(page.locator("#section-sources")).toHaveClass(/active/);
}

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
    await openSettings(page);

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
    await openSettings(page);

    const token = page.locator(
      "[data-notify-channel='telegram'] [data-channel-field='bot_token']",
    );
    await expect(token).toBeVisible({ timeout: 10_000 });
    await expect(token).toHaveAttribute("type", "password");
    await expect(token).toHaveAttribute("autocomplete", "new-password");
  });

  test("logged-in users get an explicit add-account action", async ({ page, request }) => {
    await setE2EState(request, { account: "logged_in", llm: "ready" });
    await gotoOverview(page);

    await expect(page.locator("#sidebar-login")).toBeHidden();
    await expect(page.locator("#sidebar-add-account")).toBeVisible({ timeout: 10_000 });
    await expect(page.locator("#sidebar-add-account")).toHaveText("添加账号");
  });

  test("formal Settings and Data Sources sections own their configuration surfaces", async ({ page, request }) => {
    await setE2EState(request, { account: "logged_in", llm: "ready" });
    await page.route("**/api/settings/proxy", async (route) => {
      if (route.request().method() !== "GET") return route.continue();
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          uid: 123456,
          editable: true,
          effective_source: "account",
          effective_proxy: "http://***@proxy.example.com:8080",
          env_override: false,
          account_configured: true,
          account_proxy: "http://***@proxy.example.com:8080",
          global_configured: false,
          global_proxy: null,
        }),
      });
    });
    await page.route("**/api/source-settings", async (route) => {
      if (route.request().method() !== "GET") return route.continue();
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          ds8: { dynamic_ids: ["123456789012345678"], count: 1 },
          ds9: { tags: ["抽奖"], count: 1 },
          ds10: {
            entries: [
              {
                id: "a".repeat(64),
                kind: "https",
                display: "https://api.example.com/lottery.json?token=%2A%2A%2A",
              },
            ],
            count: 1,
            file_scope: "BINGGO_HOME",
          },
        }),
      });
    });

    await gotoOverview(page);

    // 操作工具不应被误归类为设置。
    await expect(page.locator("#section-overview .extra-tools-panel")).toBeVisible({ timeout: 10_000 });
    await expect(page.locator("#section-overview #extra-panel-logs")).toBeVisible();

    await openSettings(page);
    await expect(page.locator("#section-settings .participate-settings")).toBeVisible();
    await expect(page.locator("#section-settings #llm-settings-panel")).toBeVisible();
    await expect(page.locator("#section-settings #extra-panel-enhance")).toBeVisible();
    await expect(page.locator("#section-settings #extra-panel-notify")).toBeVisible();
    await expect(page.locator("#section-settings #settings-proxy-panel")).toBeVisible();
    await expect(page.locator("[data-proxy-effective]")).toHaveText("http://***@proxy.example.com:8080");
    await expect(page.locator("[data-proxy-input]")).toHaveAttribute("type", "password");

    await openSources(page);
    await expect(page.locator("#managed-source-settings")).toBeVisible();
    await expect(page.locator("[data-ds8-input]")).toHaveValue("123456789012345678");
    await expect(page.locator("[data-ds9-input]")).toHaveValue("抽奖");
    await expect(page.locator("[data-ds10-list]")).toContainText("token=%2A%2A%2A");
    await expect(page.locator("[data-ds10-input]")).toHaveAttribute("type", "password");
  });

  test("single activity dry-run sends dry_run=true and renders preview success semantics", async ({ page, request }) => {
    await setE2EState(request, { account: "logged_in", llm: "ready" });
    let posted: Record<string, any> | null = null;

    await page.route("**/api/jobs", async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      posted = route.request().postDataJSON() as Record<string, any>;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, job: { id: 9901, state: "running", action: "participate" } }),
      });
    });
    await page.route("**/api/jobs/current", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: 9901,
          state: "success",
          action: "participate",
          message: "预演完成，未实际请求 B 站",
          progress_step: 5,
          progress_total: 5,
          finished_at: "2026-08-11T09:00:00Z",
          result: {
            dynamic_id: "123456789012345678",
            lottery_type: "转发抽奖",
            status: "dry_run",
            message: "预演完成，未实际请求 B 站",
            action_text: "好运连连！",
            actions: [
              { action: "like", ok: true, detail: "dry-run" },
              { action: "follow", ok: true, detail: "dry-run" },
              { action: "favorite", ok: true, detail: "dry-run" },
              { action: "repost", ok: true, detail: "dry-run" },
              { action: "comment", ok: true, detail: "dry-run" },
            ],
          },
        }),
      });
    });

    await gotoOverview(page);
    await page.locator("[data-section='activities']").click();
    await expect(page.locator("#section-activities")).toHaveClass(/active/);

    const preview = page.locator("[data-action='participate'][data-dry-run='true']").first();
    await expect(preview).toBeVisible({ timeout: 10_000 });
    await preview.click();

    await expect.poll(() => posted).not.toBeNull();
    expect(posted?.action).toBe("participate");
    expect(posted?.params?.dry_run).toBe(true);

    await expect(page.locator("#job-result-banner")).toBeVisible({ timeout: 10_000 });
    await expect(page.locator("#job-result-eyebrow")).toHaveText("参与预演");
    await expect(page.locator("#job-result-title")).toHaveText("预演完成");
    await expect(page.locator("#job-result-hint")).toContainText("不会写入参与记录");
    await expect(page.locator("#job-result-body")).toContainText("将点赞");
    await expect(page.locator("#job-result-body")).toContainText("预演文案：好运连连！");
  });
});
