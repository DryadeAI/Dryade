import { defineConfig } from "@playwright/test";
import path from "path";

const screenshotDir = path.resolve(
  __dirname,
  "../../internal-docs/fundraising/trails/screenshots"
);

export default defineConfig({
  testDir: ".",
  testMatch: ["*.ts"],
  testIgnore: ["playwright.config.ts"],
  timeout: 120_000,
  expect: {
    timeout: 15_000,
  },
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  use: {
    browserName: "chromium",
    headless: true,
    screenshot: "on",
    viewport: { width: 1280, height: 900 },
    actionTimeout: 10_000,
  },
  outputDir: screenshotDir,
});
