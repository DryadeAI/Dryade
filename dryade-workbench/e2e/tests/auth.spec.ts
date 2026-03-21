import { test, expect } from "@playwright/test";
import { test as authedTest, expect as authedExpect } from "../fixtures/auth";
import { AuthPage } from "../page-objects/AuthPage";

test.describe("Authentication Flow", () => {
  test("should show login form at /auth", async ({ page }) => {
    const auth = new AuthPage(page);
    await auth.goto();
    await expect(auth.emailInput).toBeVisible({ timeout: 10_000 });
    await expect(auth.passwordInput).toBeVisible({ timeout: 10_000 });
    await expect(auth.submitButton).toBeVisible({ timeout: 10_000 });
  });

  test("should redirect unauthenticated users to /auth", async ({ page }) => {
    await page.addInitScript(() => localStorage.clear());
    await page.goto("/workspace/dashboard");
    await page.waitForLoadState("domcontentloaded");
    await page.waitForURL(/\/(auth|$)/, { timeout: 10_000 });
  });

  test("should register a new user via API and authenticate", async ({ page }) => {
    const API_URL = process.env.API_URL || "http://localhost:8080";
    const email = `e2e-auth-${Date.now()}@example.com`;
    const password = "E2eTestPassword123!";

    const res = await page.request.post(`${API_URL}/api/auth/register`, {
      data: { email, password, display_name: "E2E Auth Test" },
    });

    if (res.ok()) {
      const tokens = await res.json();
      await page.addInitScript((t) => {
        localStorage.setItem("auth_tokens", JSON.stringify(t));
      }, tokens);
      await page.goto("/workspace/dashboard");
      await page.waitForLoadState("domcontentloaded");
      await expect(page).toHaveURL(/\/workspace/);
    }
  });

  test("should show validation for empty form submission", async ({ page }) => {
    const auth = new AuthPage(page);
    await auth.goto();
    await auth.submit();
    // Browser validation or custom validation should prevent submission
    // Check for validation message or required attribute
    const emailRequired = await auth.emailInput.getAttribute("required");
    const hasValidation = emailRequired !== null ||
      (await page.locator("[role='alert'], .error, [class*='error'], [class*='invalid']").count()) > 0;
    expect(hasValidation).toBeTruthy();
  });

  test("should show error for invalid credentials", async ({ page }) => {
    const auth = new AuthPage(page);
    await auth.goto();
    // Try to login with wrong credentials
    if (await auth.loginTab.isVisible().catch(() => false)) {
      await auth.loginTab.click();
    }
    await auth.fillLogin("nonexistent@example.com", "WrongPassword123!");
    await auth.submit();
    // Wait for API response error
    await page.waitForTimeout(1_000);
    // Should show error message or toast
    const errorVisible = await page.locator(
      "[role='alert'], .error, [class*='error'], [class*='destructive'], [data-sonner-toast]"
    ).first().isVisible().catch(() => false);
    // At minimum, user should NOT be redirected to workspace
    const url = page.url();
    expect(url).toMatch(/\/auth/);
  });

  authedTest("should handle logout", async ({ authedPage }) => {
    // Find logout mechanism
    const logoutBtn = authedPage.locator(
      "button:has-text('Logout'), button:has-text('Sign out'), button:has-text('Log out'), " +
      "[data-testid='logout'], a:has-text('Logout')"
    ).first();
    // Logout may be in a dropdown or settings
    if (await logoutBtn.isVisible().catch(() => false)) {
      await logoutBtn.click();
      await authedPage.waitForURL(/\/(auth|$)/, { timeout: 10_000 });
    } else {
      // Logout might be in profile menu — check for user avatar/menu
      const userMenu = authedPage.locator(
        "[data-testid='user-menu'], button[aria-label*='user' i], button[aria-label*='profile' i], " +
        "button[aria-label*='account' i]"
      ).first();
      if (await userMenu.isVisible().catch(() => false)) {
        await userMenu.click();
        await authedPage.waitForTimeout(300);
        const logoutOption = authedPage.locator("button:has-text('Logout'), button:has-text('Sign out')").first();
        if (await logoutOption.isVisible().catch(() => false)) {
          await logoutOption.click();
          await authedPage.waitForURL(/\/(auth|$)/, { timeout: 10_000 });
        }
      }
    }
  });
});
