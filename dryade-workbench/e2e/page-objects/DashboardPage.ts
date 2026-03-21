import type { Page, Locator } from "@playwright/test";

export class DashboardPage {
  readonly page: Page;
  readonly heading: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole("heading", { level: 1 });
  }

  async goto() {
    await this.page.goto("/workspace/dashboard");
    await this.page.waitForLoadState("domcontentloaded");
  }

  async waitForLoad() {
    // Wait for the workspace layout wrapper or the dashboard container itself.
    // During loading state, the dashboard renders a skeleton <div> (not <main>),
    // so we wait for either the layout #main-content or the dashboard data-testid.
    await this.page.locator("#main-content, [data-testid='dashboard-container']").first().waitFor({ state: "visible", timeout: 30_000 });
  }

  async getQuickActions() {
    return this.page.locator("[data-testid='quick-action'], button:has-text('New'), a:has-text('New')").all();
  }

  async isLoaded() {
    return this.page.locator("main").isVisible();
  }

  /** Returns the stat cards grid (Total Requests, Success Rate, Active Agents, Queue Status) */
  async getStatCards() {
    return this.page.locator(".grid > div").filter({
      has: this.page.locator("p, span"),
    }).all();
  }

  /** Returns the recent activity sections (Execution History + Recent Requests) */
  async getRecentActivity() {
    return this.page.locator(".glass-card").all();
  }

  /** Returns the greeting/welcome heading (Good morning/afternoon/evening) */
  getWelcomeMessage() {
    return this.heading;
  }
}
