import type { Page, Locator } from "@playwright/test";

export class MetricsPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly refreshButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole("heading").first();
    this.refreshButton = page.getByRole("button", { name: "Refresh", exact: true });
  }

  async goto() {
    await this.page.goto("/workspace/metrics");
    await this.page.waitForLoadState("domcontentloaded");
    await this.page.waitForTimeout(2_000);
  }

  /** Returns all metric stat cards (Total Requests, Avg Latency, etc.) */
  async getMetricCards() {
    // StatsCard components in the stats grid at the top
    const cards = await this.page
      .locator(".grid > div")
      .filter({ has: this.page.locator("p.text-2xl, [class*='text-2xl'], span.text-2xl") })
      .all();
    if (cards.length > 0) return cards;
    // Fallback: any grid children
    return this.page.locator(".grid > div").all();
  }

  /** Returns all chart containers (recharts renders inside ResponsiveContainer) */
  async getCharts() {
    return this.page.locator(".recharts-wrapper, [role='img']").all();
  }

  /** Returns the requests table (recent requests tab) */
  getRequestsTable() {
    return this.page.getByRole("table").first();
  }

  /** Returns the time period selector */
  getTimePeriodSelector() {
    return this.page.locator("select, [role='combobox']").first();
  }

  /** Returns tab triggers */
  getTab(name: string) {
    return this.page.getByRole("tab", { name: new RegExp(name, "i") });
  }
}
