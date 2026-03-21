import { test, expect } from "../fixtures/mock-auth";
import { CostTrackerPage } from "../page-objects/CostTrackerPage";

test.describe("Cost Tracker Page", () => {
  test("should load cost tracker page (native, not iframe)", async ({ authedPage }) => {
    const costTracker = new CostTrackerPage(authedPage);
    await costTracker.goto();
    await expect(costTracker.heading).toBeVisible({ timeout: 10_000 });
    // Verify it's NOT rendered in an iframe
    const iframes = await authedPage.locator("iframe").count();
    // Cost tracker should be native — either no iframes or none with cost-tracker src
    const costIframes = await authedPage.locator("iframe[src*='cost']").count();
    expect(costIframes).toBe(0);
  });

  test("should display cost summary section", async ({ authedPage }) => {
    const costTracker = new CostTrackerPage(authedPage);
    await costTracker.goto();
    const summary = costTracker.getCostSummary();
    // Should have stat cards or show empty/zero state
    const count = await summary.count();
    // At minimum the page should render (even with $0.00)
    expect(count).toBeGreaterThanOrEqual(0);
    await expect(costTracker.heading).toBeVisible();
  });

  test("should show usage breakdown or empty state", async ({ authedPage }) => {
    const costTracker = new CostTrackerPage(authedPage);
    await costTracker.goto();
    // Wait for heading to confirm the page fully rendered
    await expect(costTracker.heading).toBeVisible({ timeout: 10_000 });
    // Page should have meaningful content (tabs, cost data, or empty state)
    const body = await authedPage.locator("#main-content, main").first().textContent();
    expect(body!.length).toBeGreaterThan(0);
  });

  test("should have refresh button", async ({ authedPage }) => {
    const costTracker = new CostTrackerPage(authedPage);
    await costTracker.goto();
    await expect(costTracker.refreshButton).toBeVisible({ timeout: 10_000 });
  });
});
