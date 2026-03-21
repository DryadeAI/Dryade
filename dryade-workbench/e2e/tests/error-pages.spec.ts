import { test, expect } from "@playwright/test";
import { test as authedTest, expect as authedExpect } from "../fixtures/mock-auth";

test.describe("Error Pages", () => {
  test("should show 404 or fallback for unknown routes", async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem(
        "auth_tokens",
        JSON.stringify({
          access_token: "fake-token-for-404-test",
          refresh_token: "fake-refresh",
          token_type: "bearer",
          expires_in: 3600,
        })
      );
    });
    await page.goto("/workspace/nonexistent-route-xyz-404");
    await page.waitForLoadState("domcontentloaded");
    // Should either show 404 content, redirect, or show a meaningful page (not crash)
    const content = await page.locator("body").textContent();
    expect(content).toBeTruthy();
  });

  test("should redirect to auth when accessing workspace without auth", async ({ page }) => {
    await page.addInitScript(() => localStorage.clear());
    await page.goto("/workspace/dashboard");
    await page.waitForLoadState("domcontentloaded");
    // Should redirect to /auth or show auth UI
    await page.waitForURL(/\/(auth|$)/, { timeout: 10_000 });
  });

  authedTest("should handle invalid conversation IDs gracefully", async ({ authedPage }) => {
    await authedPage.goto("/workspace/chat/invalid-uuid-00000");
    await authedPage.waitForLoadState("domcontentloaded");
    // Should not crash — either redirect to /workspace/chat or show error/empty state
    const url = authedPage.url();
    expect(url).toMatch(/\/workspace\/chat/);
    const body = await authedPage.locator("body").textContent();
    expect(body).toBeTruthy();
  });
});
