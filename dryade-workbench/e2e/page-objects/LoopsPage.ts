import type { Page, Locator } from "@playwright/test";

export class LoopsPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly createButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole("heading").first();
    this.createButton = page.getByRole("button", { name: /new loop/i });
  }

  async goto() {
    await this.page.goto("/workspace/loops");
    await this.page.waitForLoadState("domcontentloaded");
    await this.page.waitForTimeout(2_000);
  }

  /** Returns all loop rows in the table */
  async getLoopList() {
    return this.page.getByRole("row").all();
  }

  /** Returns the "New Loop" create button */
  getCreateButton() {
    return this.createButton;
  }

  /** Returns a loop row by matching loop name text */
  getLoopByName(name: string) {
    return this.page.getByRole("row").filter({ hasText: name }).first();
  }

  /** Returns the status badge within a loop row */
  getLoopStatus(name: string) {
    const row = this.getLoopByName(name);
    return row.locator("span, [class*='badge']").first();
  }

  /** Returns the empty state element when no loops exist */
  getEmptyState() {
    return this.page.getByText("No scheduled loops");
  }
}
