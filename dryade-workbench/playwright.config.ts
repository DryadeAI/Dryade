import { defineConfig, devices } from "@playwright/test";
import { createRequire } from "module";
const require = createRequire(import.meta.url);

export default defineConfig({
  testDir: "./e2e/tests",
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? "github" : "html",
  use: {
    baseURL: process.env.BASE_URL || "https://localhost:9005",
    ignoreHTTPSErrors: true,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  projects: [
    {
      // Community tests — excludes @real-llm, @plugin, and @deep tests (CI default)
      // Run with: npx playwright test --project=community
      name: "community",
      use: { ...devices["Desktop Chrome"] },
      grep: /^((?!@real-llm|@plugin|@deep).)*$/,
    },
    {
      // Standard fast tests — excludes @real-llm tests (which require GPU)
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
      grep: /^((?!@real-llm).)*$/,
    },
    {
      // Real LLM tests — requires running backend with GPU and LLM loaded
      // Run with: npx playwright test --project=real-llm
      name: "real-llm",
      use: { ...devices["Desktop Chrome"] },
      grep: /@real-llm/,
      timeout: 300_000,
    },
    {
      // Deep functional E2E tests — single shared user, real backend, serial execution
      // Run with: npx playwright test --project=deep
      name: "deep",
      use: { ...devices["Desktop Chrome"] },
      grep: /@deep/,
      timeout: 120_000,
      testDir: "./e2e/tests/deep",
      globalSetup: require.resolve("./e2e/global-setup"),
      fullyParallel: false,
    },
  ],
  webServer: process.env.CI
    ? undefined
    : {
        command: "npm run dev",
        port: 9005,
        reuseExistingServer: true,
      },
});
