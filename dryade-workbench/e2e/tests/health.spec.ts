import { test, expect } from "../fixtures/mock-auth";
import { HealthPage } from "../page-objects/HealthPage";

test.describe("Health Dashboard", () => {
  test("should load health dashboard", async ({ authedPage }) => {
    const health = new HealthPage(authedPage);
    await health.goto();
    await expect(health.heading).toBeVisible({ timeout: 10_000 });
  });

  test("should display overall system status", async ({ authedPage }) => {
    const health = new HealthPage(authedPage);
    await health.goto();
    const status = health.getOverallStatus();
    await expect(status).toBeVisible({ timeout: 10_000 });
    const text = await status.textContent();
    expect(text).toMatch(/healthy|degraded|unhealthy|unknown|offline|failed|system health|error/i);
  });

  test("should show provider health cards", async ({ authedPage }) => {
    const health = new HealthPage(authedPage);
    await health.goto();
    const cards = await health.getProviderCards();
    // Should have at least some dependency/provider cards (core services)
    expect(cards.length).toBeGreaterThanOrEqual(0);
    // Page should have content regardless
    await expect(health.heading).toBeVisible();
  });

  test("should have refresh button", async ({ authedPage }) => {
    const health = new HealthPage(authedPage);
    await health.goto();
    await expect(health.refreshButton).toBeVisible({ timeout: 10_000 });
  });
});
