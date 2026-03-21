/**
 * Deep test fixture for deep E2E tests.
 *
 * Extends the base Playwright test with storageState from the global-setup
 * shared user (deep-e2e@example.com). Provides:
 * - authedPage: page with storageState already loaded, navigated to dashboard
 * - accessToken: raw JWT access_token string (fresh login per test)
 * - apiClient: APIRequestContext with Authorization header preset
 */

import {
  test as base,
  type APIRequestContext,
  type Page,
} from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const API_URL = process.env.API_URL || "http://localhost:8080";

/**
 * Selector for assistant messages in chat.
 * MessageItem.tsx uses prose wrapper with border-l-2 border-primary/50 styling.
 * No data-role attributes exist, so we match the structural pattern.
 */
export const ASSISTANT_MSG_SELECTOR =
  ".prose, [class*='border-l-2'][class*='border-primary']";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const STORAGE_STATE_PATH = path.join(
  __dirname,
  "..",
  ".auth",
  "deep-storage-state.json",
);

const DEEP_USER = {
  email: "deep-e2e@example.com",
  password: "DeepE2ePassword1234",
};

export const test = base.extend<{
  authedPage: Page;
  accessToken: string;
  apiClient: APIRequestContext;
}>({
  storageState: STORAGE_STATE_PATH,

  authedPage: async ({ page, playwright }, use) => {
    // Refresh auth tokens before each test to avoid 30min JWT expiry
    try {
      const reqCtx = await playwright.request.newContext({
        baseURL: API_URL,
        ignoreHTTPSErrors: true,
      });
      let loginRes = await reqCtx.post("/api/auth/login", {
        data: {
          email: DEEP_USER.email,
          password: DEEP_USER.password,
        },
        timeout: 30_000,
      });
      // Retry once if backend was slow (overloaded from prior test)
      if (!loginRes.ok()) {
        await new Promise((r) => setTimeout(r, 3_000));
        loginRes = await reqCtx.post("/api/auth/login", {
          data: {
            email: DEEP_USER.email,
            password: DEEP_USER.password,
          },
          timeout: 30_000,
        });
      }
      if (loginRes.ok()) {
        const tokens = await loginRes.json();
        // Set tokens via page evaluate on the app origin
        await page.goto("/", { waitUntil: "commit" });
        await page.evaluate((t) => {
          localStorage.setItem("auth_tokens", JSON.stringify(t));
        }, tokens);
      }
      await reqCtx.dispose();
    } catch {
      // Proceed with existing storage state
    }
    await page.goto("/workspace/dashboard");
    await page.waitForLoadState("domcontentloaded");
    // Verify not redirected to login
    if (page.url().includes("/login") || page.url().includes("/auth")) {
      // Last resort: do UI login
      await page.fill('input[type="email"], input[name="email"]', DEEP_USER.email);
      await page.fill('input[type="password"], input[name="password"]', DEEP_USER.password);
      await page.click('button[type="submit"], button:has-text("Sign In")');
      await page.waitForURL(/workspace/, { timeout: 30_000 }).catch(() => {});
    }
    await use(page);
  },

  accessToken: async ({ playwright }, use) => {
    // Get a fresh token via login API to avoid expiration during long test runs
    const ctx = await playwright.request.newContext({
      baseURL: API_URL,
      ignoreHTTPSErrors: true,
    });
    try {
      const loginRes = await ctx.post("/api/auth/login", {
        data: {
          email: DEEP_USER.email,
          password: DEEP_USER.password,
        },
      });
      if (loginRes.ok()) {
        const body = await loginRes.json();
        await use(body.access_token ?? "");
      } else {
        // Fallback: try localStorage from storageState
        await use("");
      }
    } finally {
      await ctx.dispose().catch(() => {});
    }
  },

  apiClient: async ({ playwright, accessToken }, use) => {
    const ctx = await playwright.request.newContext({
      baseURL: API_URL,
      ignoreHTTPSErrors: true,
      extraHTTPHeaders: { Authorization: `Bearer ${accessToken}` },
    });
    // Wrap with auto-retry on 429 for all HTTP methods
    const retryMethods = new Set(["get", "post", "put", "patch", "delete", "head", "fetch"]);
    const proxy = new Proxy(ctx, {
      get(target, prop, receiver) {
        const val = Reflect.get(target, prop, receiver);
        if (typeof prop === "string" && retryMethods.has(prop) && typeof val === "function") {
          return async (...args: unknown[]) => {
            for (let attempt = 0; attempt < 6; attempt++) {
              const res = await (val as Function).apply(target, args);
              if (res.status() !== 429) return res;
              const retryAfter = Number(res.headers()["retry-after"] || "2");
              await new Promise((r) => setTimeout(r, (retryAfter + 1 + attempt) * 1000));
            }
            return await (val as Function).apply(target, args);
          };
        }
        return typeof val === "function" ? val.bind(target) : val;
      },
    }) as APIRequestContext;
    await use(proxy);
    await ctx.dispose().catch(() => {});
  },
});

export { expect } from "@playwright/test";

/**
 * Retry helper for API calls that may hit 429 rate limits.
 * Retries up to `maxRetries` times with exponential backoff.
 */
export async function retryApi<T>(
  fn: () => Promise<T & { status: () => number; headers: () => Record<string, string> }>,
  maxRetries = 6,
): Promise<T & { status: () => number; headers: () => Record<string, string> }> {
  let res: T & { status: () => number; headers: () => Record<string, string> };
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    res = await fn();
    if (res.status() !== 429) return res;
    const retryAfter = Number(res.headers()["retry-after"] || "2");
    await new Promise((r) => setTimeout(r, (retryAfter + 1 + attempt) * 1000));
  }
  return res!;
}
