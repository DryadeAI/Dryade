import { test, expect } from "../fixtures/mock-auth";
import { AgentsPage } from "../page-objects/AgentsPage";

test.describe("Agents Page", () => {
  test("should load agents page with heading", async ({ authedPage }) => {
    const agents = new AgentsPage(authedPage);
    await agents.goto();
    await expect(agents.heading).toBeVisible({ timeout: 10_000 });
  });

  test("should display agent cards or empty state", async ({ authedPage }) => {
    const agents = new AgentsPage(authedPage);
    await agents.goto();
    // Wait for loading skeleton to disappear (or timeout = never appeared)
    await agents.getLoadingSkeleton().waitFor({ state: "hidden", timeout: 15_000 }).catch(() => {});
    // Give React a moment to render the post-loading state
    await authedPage.waitForLoadState("domcontentloaded");
    const count = await agents.getAgentCount();
    if (count === 0) {
      // No agents registered — page should still render heading and filter tabs
      // (the screenshot shows "Agents" heading + framework tabs with 0 counts)
      await expect(agents.heading).toBeVisible({ timeout: 5_000 });
      const tablist = authedPage.locator("[role='tablist']").first();
      await expect(tablist).toBeVisible({ timeout: 5_000 });
    } else {
      expect(count).toBeGreaterThan(0);
    }
  });

  test("should show agent details on card click", async ({ authedPage }) => {
    const agents = new AgentsPage(authedPage);
    await agents.goto();
    await expect(agents.getLoadingSkeleton()).toBeHidden({ timeout: 15_000 });
    const count = await agents.getAgentCount();
    if (count > 0) {
      const cards = await agents.getAgentCards();
      await cards[0].click();
      // Detail panel should appear
      const detailPanel = authedPage.locator("[class*='border-l'], [class*='sheet'], [role='dialog']").first();
      await expect(detailPanel).toBeVisible({ timeout: 5_000 });
    }
  });

  test("should have search functionality", async ({ authedPage }) => {
    const agents = new AgentsPage(authedPage);
    await agents.goto();
    await expect(agents.getLoadingSkeleton()).toBeHidden({ timeout: 15_000 });
    // AgentSearchBar renders an input
    const searchInput = authedPage.locator("input[placeholder*='search' i], input[placeholder*='Search' i]").first();
    await expect(searchInput).toBeVisible({ timeout: 5_000 });
  });

  test("should have framework filter tabs", async ({ authedPage }) => {
    const agents = new AgentsPage(authedPage);
    await agents.goto();
    // Wait for the filter tabs container to appear (rendered above the grid)
    const tablist = authedPage.locator("[role='tablist'][aria-label='Filter agents by framework']");
    await expect(tablist).toBeVisible({ timeout: 15_000 });
    // FrameworkFilterTabs renders tab buttons with role="tab"
    const allTab = authedPage.getByRole("tab", { name: /all/i }).first();
    await expect(allTab).toBeVisible({ timeout: 5_000 });
  });
});
