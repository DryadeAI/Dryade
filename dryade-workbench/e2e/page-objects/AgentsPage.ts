import type { Page, Locator } from "@playwright/test";

export class AgentsPage {
  readonly page: Page;
  readonly heading: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole("heading", { level: 1 });
  }

  async goto() {
    await this.page.goto("/workspace/agents");
    await this.page.waitForLoadState("domcontentloaded");
    // Wait for either the agents list or loading skeleton to appear
    await this.page.locator("[data-testid='agents-list'], [aria-label='Loading agents']").first().waitFor({ state: "visible", timeout: 15_000 }).catch(() => {});
  }

  /** Returns all agent cards in the grid (aria-label="Agents list" on the grid) */
  async getAgentCards() {
    // AgentCard renders as <button role="gridcell">, not <div>
    return this.page
      .locator("[aria-label='Agents list'] > [role='gridcell'], [data-testid='agents-list'] > [role='gridcell']")
      .all();
  }

  /** Returns a specific agent card by agent name text */
  getAgentByName(name: string) {
    return this.page
      .locator("[aria-label='Agents list'] > [role='gridcell'], [data-testid='agents-list'] > [role='gridcell']")
      .filter({ hasText: name })
      .first();
  }

  /** Clicks on an agent card to open the detail panel */
  async gotoDetail(agentName: string) {
    const card = this.getAgentByName(agentName);
    await card.click();
    // Wait for detail panel to appear
    await this.page.waitForTimeout(300);
  }

  /** Returns the count of agent cards */
  async getAgentCount() {
    const cards = await this.getAgentCards();
    return cards.length;
  }

  /** Returns the loading skeleton container */
  getLoadingSkeleton() {
    return this.page.locator("[aria-label='Loading agents']");
  }
}
