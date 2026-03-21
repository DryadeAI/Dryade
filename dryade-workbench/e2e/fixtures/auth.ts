import { test as base, type Page } from "@playwright/test";

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
    data: { email, password, display_name: "E2E User" },
  });

  if (res.ok()) {
    return res.json();
  }

  // Already registered - login instead
  const loginRes = await page.request.post(`${API_URL}/api/auth/login`, {
    data: { email, password },
  });
  return loginRes.json();
}

/**
 * Extended test fixture that provides an authenticated page.
 * Sets auth_tokens in localStorage before each test.
 */
export const test = base.extend<{ authedPage: Page }>({
  authedPage: async ({ page }, use) => {
    const email = `e2e-${Date.now()}@example.com`;
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
});

export { expect } from "@playwright/test";
