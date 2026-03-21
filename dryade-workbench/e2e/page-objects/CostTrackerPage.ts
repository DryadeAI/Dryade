import type { Page, Locator } from "@playwright/test";

export class CostTrackerPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly refreshButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole("heading").first();
    this.refreshButton = page.getByRole("button", { name: /refresh/i });
  }

  async goto() {
    await this.page.goto("/workspace/cost-tracker");
    await this.page.waitForLoadState("domcontentloaded");
    await this.page.waitForTimeout(2_000);
  }

  /** Returns the 4 summary stats cards (Total Cost, Total Tokens, Requests, Avg per Request) */
  getCostSummary() {
    // StatsCard components in the stats grid — try multiple text size classes
    return this.page.locator(".grid > div").filter({
      has: this.page.locator("p.text-2xl, [class*='text-2xl'], p.text-xl, [class*='text-xl'], span.font-bold"),
    });
  }

  /** Returns the records table (visible on the "records" tab) */
  getUsageTable() {
    return this.page.getByRole("table").first();
  }

  /** Returns the time range selector (period dropdown) */
  getTimeRange() {
    return this.page.locator("select").first();
  }

  /** Returns the Live ticker card with realtime cost */
  getLiveTicker() {
    return this.page.getByText("Live").first();
  }

  /** Returns tab triggers for the cost breakdown tabs */
  getTab(name: string) {
    return this.page.getByRole("tab", { name: new RegExp(name, "i") });
  }
}
