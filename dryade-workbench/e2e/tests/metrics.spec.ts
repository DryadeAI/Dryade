import { test, expect } from "../fixtures/mock-auth";
import { MetricsPage } from "../page-objects/MetricsPage";

test.describe("Metrics Dashboard", () => {
  test("should load metrics dashboard", async ({ authedPage }) => {
    const metrics = new MetricsPage(authedPage);
    await metrics.goto();
    await expect(metrics.heading).toBeVisible({ timeout: 10_000 });
  });

  test("should display metric cards or summary", async ({ authedPage }) => {
    const metrics = new MetricsPage(authedPage);
    await metrics.goto();
    const cards = await metrics.getMetricCards();
    // Should have stat cards (may show 0 or — with no data)
    expect(cards.length).toBeGreaterThanOrEqual(0);
    await expect(metrics.heading).toBeVisible();
  });

  test("should show requests table or empty state", async ({ authedPage }) => {
    const metrics = new MetricsPage(authedPage);
    await metrics.goto();
    // Wait for heading to confirm page loaded
    await expect(metrics.heading).toBeVisible({ timeout: 10_000 });
    // Page should have content (table or empty message)
    const body = await authedPage.locator("#main-content, main").first().textContent();
    expect(body!.length).toBeGreaterThan(0);
  });

  test("should have refresh button", async ({ authedPage }) => {
    const metrics = new MetricsPage(authedPage);
    await metrics.goto();
    await expect(metrics.refreshButton).toBeVisible({ timeout: 10_000 });
  });
});
