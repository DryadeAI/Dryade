import type { Page, Locator } from "@playwright/test";

export class FactoryPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly createButton: Locator;
  readonly searchInput: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole("heading").first();
    this.createButton = page.getByRole("button", { name: /create/i }).first();
    this.searchInput = page.getByLabel("Search artifacts");
  }

  async goto() {
    await this.page.goto("/workspace/factory");
    await this.page.waitForLoadState("domcontentloaded");
  }

  /** Returns all artifact cards in the grid */
  async getContent() {
    return this.page
      .locator(".grid > div")
      .all();
  }

  /** Returns the create artifact button */
  getCreateButton() {
    return this.createButton;
  }

  /** Returns the search input for filtering artifacts */
  getSearchInput() {
    return this.searchInput;
  }

  /** Returns the type filter buttons (all, agent, tool, skill) */
  getTypeFilters() {
    return this.page.locator("header button[size='sm'], header .flex button").filter({
      hasText: /all|agent|tool|skill/i,
    });
  }
}
