/**
 * API fixture for workflow E2E tests.
 *
 * Extends the base Playwright test with:
 * - authedPage: authenticated browser page (JWT in localStorage)
 * - accessToken: raw JWT access_token string for direct HTTP calls
 * - apiClient: APIRequestContext with Authorization header preset
 *
 * Uses @example.com email domain (not @test.local) to avoid
 * Pydantic email validation rejecting reserved TLDs.
 */

import { test as base, type APIRequestContext, type Page } from "@playwright/test";

const API_URL = process.env.API_URL || "http://localhost:8080";

interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

async function registerAndLogin(
  page: Page,
  email: string,
  password: string,
): Promise<AuthTokens> {
  const res = await page.request.post(`${API_URL}/api/auth/register`, {
    data: { email, password, display_name: "E2E Workflow User" },
  });

  if (res.ok()) {
    return res.json();
  }

  // Already registered — fall back to login
  const loginRes = await page.request.post(`${API_URL}/api/auth/login`, {
    data: { email, password },
  });
  return loginRes.json();
}

export const test = base.extend<{
  authedPage: Page;
  accessToken: string;
  apiClient: APIRequestContext;
}>({
  authedPage: async ({ page }, use) => {
    const email = `e2e-wf-${Date.now()}@example.com`;
    const password = "E2eTestPassword123!";

    const tokens = await registerAndLogin(page, email, password);

    // Set tokens in localStorage (matches AuthContext.tsx key)
    await page.addInitScript((t) => {
      localStorage.setItem("auth_tokens", JSON.stringify(t));
    }, tokens);

    await page.goto("/workspace/dashboard");
    await page.waitForLoadState("domcontentloaded");
    await use(page);
  },

  accessToken: async ({ authedPage }, use) => {
    // Pull the stored access_token from localStorage after authedPage is ready
    const rawTokens = await authedPage.evaluate(() =>
      localStorage.getItem("auth_tokens"),
    );
    const tokens: Partial<AuthTokens> = JSON.parse(rawTokens ?? "{}");
    await use(tokens.access_token ?? "");
  },

  apiClient: async ({ playwright, accessToken }, use) => {
    const ctx = await playwright.request.newContext({
      baseURL: API_URL,
      extraHTTPHeaders: { Authorization: `Bearer ${accessToken}` },
    });
    await use(ctx);
    await ctx.dispose();
  },
});

export { expect } from "@playwright/test";

export { API_URL };
