/**
 * Mock auth fixture for community E2E tests.
 *
 * Injects fake JWT tokens into localStorage WITHOUT calling the backend API.
 * This allows UI-rendering tests to run without a live backend.
 *
 * The frontend reads `auth_tokens` from localStorage to determine auth state.
 * For pure UI tests (navigation, component rendering, page structure),
 * a fake token is sufficient -- the SPA renders the workspace layout.
 *
 * Tests that make actual API calls (create workflows, fetch data) will still
 * need a live backend and should use `fixtures/auth.ts` instead.
 */

import { test as base, type Page } from "@playwright/test";

const FAKE_TOKENS = {
  access_token: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJlMmUtbW9jay11c2VyQGV4YW1wbGUuY29tIiwiZXhwIjo5OTk5OTk5OTk5LCJpYXQiOjE3MDAwMDAwMDAsInJvbGUiOiJ1c2VyIiwiZGlzcGxheV9uYW1lIjoiRTJFIE1vY2sgVXNlciJ9.mock-signature",
  refresh_token: "mock-refresh-token",
  token_type: "bearer",
  expires_in: 3600,
};

/**
 * Extended test fixture providing a page with mock auth tokens in localStorage.
 * No backend calls are made -- tokens are injected directly.
 */
export const test = base.extend<{ authedPage: Page }>({
  authedPage: async ({ page }, use) => {
    // Inject fake tokens before navigating
    await page.addInitScript((tokens) => {
      localStorage.setItem("auth_tokens", JSON.stringify(tokens));
    }, FAKE_TOKENS);

    await page.goto("/workspace/dashboard");
    await page.waitForLoadState("domcontentloaded");
    await use(page);
  },
});

export { expect } from "@playwright/test";
