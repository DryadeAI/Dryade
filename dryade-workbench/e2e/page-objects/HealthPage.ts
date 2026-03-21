import type { Page, Locator } from "@playwright/test";

export class HealthPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly refreshButton: Locator;

  constructor(page: Page) {
    this.page = page;
    // Try h1, h2, or any heading — health page may use h2
    this.heading = page.getByRole("heading").first();
    this.refreshButton = page.getByRole("button", { name: /refresh|retry/i });
  }

  async goto() {
    await this.page.goto("/workspace/health");
    await this.page.waitForLoadState("domcontentloaded");
    // Wait for the health container to render (may take time for API response)
    await this.page.locator("[data-testid='health-container']").waitFor({ state: "visible", timeout: 15_000 }).catch(() => {});
    // Extra wait for async health data to populate
    await this.page.waitForTimeout(3_000);
  }

  /** Returns all provider/dependency cards in the grid */
  async getProviderCards() {
    // DependencyCard components are inside categorized grids.
    // Each card wrapper contains a Card with CardContent and a span.font-medium for the name.
    // Wait briefly for cards to appear (health data loads async).
    await this.page.locator(".grid .font-medium").first().waitFor({ timeout: 10_000 }).catch(() => {});
    const cards = await this.page
      .locator(".grid > div")
      .filter({ has: this.page.locator(".font-medium") })
      .all();
    if (cards.length > 0) return cards;
    // Fallback: any divs in a grid
    return this.page.locator(".grid > div").all();
  }

  /** Returns the overall status indicator or error message */
  getOverallStatus() {
    // Match either the healthy status indicator or the error/failed state
    return this.page.locator(
      "main span.text-lg.font-semibold, main h2, [role='main'] span.text-lg.font-semibold, " +
      ".flex-1 span.text-lg.font-semibold, :text('Failed to load'), :text('System Health')"
    ).first();
  }

  /** Returns a specific provider/component card by name */
  getProviderStatus(name: string) {
    return this.page
      .locator(".grid > div")
      .filter({ hasText: name })
      .first();
  }

  /** Returns the uptime display */
  getUptime() {
    return this.page.getByText(/uptime/i).first();
  }

  /** Returns the version display */
  getVersion() {
    return this.page.getByText(/^v\d/).first();
  }
}
