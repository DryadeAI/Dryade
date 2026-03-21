/**
 * Global setup for deep E2E tests.
 *
 * Registers a single shared user (deep-e2e@example.com) and saves
 * storageState to e2e/.auth/deep-storage-state.json for reuse
 * across all deep test specs.
 */

import { chromium, type FullConfig } from "@playwright/test";
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const API_URL = process.env.API_URL || "http://localhost:8080";
const STORAGE_STATE_PATH = path.join(
  __dirname,
  ".auth",
  "deep-storage-state.json",
);

const DEEP_USER = {
  email: "deep-e2e@example.com",
  password: "DeepE2ePassword1234",
  display_name: "Deep E2E User",
};

export default async function globalSetup(_config: FullConfig) {
  // Ensure .auth directory exists
  const authDir = path.dirname(STORAGE_STATE_PATH);
  if (!fs.existsSync(authDir)) {
    fs.mkdirSync(authDir, { recursive: true });
  }

  // Register or login via API
  const requestContext = await chromium.launchPersistentContext("", {
    ignoreHTTPSErrors: true,
  });
  const page = await requestContext.newPage();

  let tokens: {
    access_token: string;
    refresh_token: string;
    token_type: string;
    expires_in: number;
  };

  // Try register first
  const registerRes = await page.request.post(
    `${API_URL}/api/auth/register`,
    {
      data: {
        email: DEEP_USER.email,
        password: DEEP_USER.password,
        name: DEEP_USER.display_name,
      },
    },
  );

  if (registerRes.ok()) {
    tokens = await registerRes.json();
  } else {
    // Already registered (409) — fall back to login
    const loginRes = await page.request.post(`${API_URL}/api/auth/login`, {
      data: {
        email: DEEP_USER.email,
        password: DEEP_USER.password,
      },
    });

    if (!loginRes.ok()) {
      const body = await loginRes.text();
      throw new Error(
        `Deep E2E global setup: login failed (${loginRes.status()}): ${body}`,
      );
    }

    tokens = await loginRes.json();
  }

  // Complete setup wizard by configuring LLM via API
  // POST /api/setup/complete marks the instance as configured so the
  // onboarding wizard doesn't appear in deep tests.
  try {
    const setupRes = await page.request.post(
      `${API_URL}/api/setup/complete`,
      {
        headers: { Authorization: `Bearer ${tokens.access_token}` },
        data: {
          llm_provider: "vllm",
          llm_api_key: "",
          llm_endpoint: "http://172.17.0.1:8000/v1",
        },
      },
    );
    if (!setupRes.ok()) {
      console.warn(
        `[global-setup] Setup complete returned ${setupRes.status()} — wizard may appear`,
      );
    }
  } catch (e) {
    console.warn(`[global-setup] Setup complete failed: ${e}`);
  }

  // Mark setup as completed in localStorage
  const baseURL = process.env.BASE_URL || "https://localhost:9005";
  await page.goto(baseURL);
  await page.evaluate((t) => {
    localStorage.setItem("auth_tokens", JSON.stringify(t));
    localStorage.setItem("setup_completed", "true");
    localStorage.setItem("onboarding_complete", "true");
  }, tokens);

  // Save storageState for reuse by all deep tests
  await requestContext.storageState({ path: STORAGE_STATE_PATH });
  await requestContext.close();
}
