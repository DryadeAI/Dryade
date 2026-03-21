import type { Page, Locator } from "@playwright/test";

export class KnowledgePage {
  readonly page: Page;
  readonly heading: Locator;
  readonly searchButton: Locator;
  readonly sourcesTab: Locator;
  readonly uploadTab: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole("heading").first();
    this.searchButton = page.getByRole("button", { name: /search/i });
    this.sourcesTab = page.getByRole("tab", { name: /sources/i });
    this.uploadTab = page.getByRole("tab", { name: /upload/i });
  }

  async goto() {
    await this.page.goto("/workspace/knowledge");
    await this.page.waitForLoadState("domcontentloaded");
    await this.page.waitForTimeout(2_000);
  }

  /** Returns all document cards in the sources grid */
  async getDocumentList() {
    // DocumentCard components render inside the sources tab grid
    // Try specific test IDs first, then grid children, then table rows
    const cards = await this.page
      .locator("[data-testid='document-card'], .grid > div, table tbody tr")
      .all();
    // Filter out empty/tiny elements
    const visible: typeof cards = [];
    for (const card of cards) {
      if (await card.isVisible().catch(() => false)) {
        visible.push(card);
      }
    }
    return visible;
  }

  /** Returns the upload tab trigger button */
  getUploadButton() {
    return this.uploadTab;
  }

  /** Returns the search dialog trigger button */
  getSearchButton() {
    return this.searchButton;
  }

  /** Returns the search input inside the search dialog */
  getSearchInput() {
    return this.page.getByLabel("Search knowledge base");
  }

  /** Returns the badge showing sources count */
  getDocumentCount() {
    // Badge next to the heading shows source count
    return this.page.locator("header .badge, h1 + span, h1 ~ span").first();
  }
}
