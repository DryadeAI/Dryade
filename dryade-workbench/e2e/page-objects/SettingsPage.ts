import type { Page, Locator } from "@playwright/test";

export class SettingsPage {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  async goto() {
    await this.page.goto("/workspace/settings");
    await this.page.waitForLoadState("domcontentloaded");
    // Wait for page content — try heading or nav buttons (whichever appears first)
    await Promise.race([
      this.page.getByText("Settings").first().waitFor({ state: "visible", timeout: 20_000 }),
      this.page.waitForSelector("nav button", { timeout: 20_000 }),
      this.page.getByRole("heading").first().waitFor({ state: "visible", timeout: 20_000 }),
    ]).catch(() => {});
    // Extra wait for lazy-loaded content
    await this.page.waitForTimeout(1_000);
  }

  async clickTab(name: string) {
    const tab = this.page.getByRole("tab", { name: new RegExp(name, "i") });
    await tab.click();
  }

  async getActiveTab(): Promise<string | null> {
    const active = this.page.locator('[role="tab"][data-state="active"]').first();
    return active.textContent();
  }

  async getTabList() {
    return this.page.locator('[role="tab"]').all();
  }

  // Legacy compatibility
  async clickSection(name: string) {
    return this.clickTab(name);
  }

  async getActiveSection(): Promise<string | null> {
    return this.getActiveTab();
  }

  async getSectionList() {
    return this.getTabList();
  }
}
