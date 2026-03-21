import { type Page, type Locator } from "@playwright/test";

/**
 * WorkflowPage page object — provides stable selectors for workflow UI tests.
 *
 * Used by:
 *   - e2e/tests/ui/execution-log.spec.ts
 *   - e2e/tests/ui/save-as-template.spec.ts
 */
export class WorkflowPage {
  readonly page: Page;
  readonly executionLog: Locator;
  readonly executionLogHeader: Locator;
  readonly executionLogList: Locator;
  readonly executionLogEntries: Locator;
  readonly workflowHeader: Locator;
  readonly scenarioList: Locator;

  constructor(page: Page) {
    this.page = page;
    this.executionLog = page.locator('[data-testid="execution-log"]');
    this.executionLogHeader = page.locator('[data-testid="execution-log-header"]');
    this.executionLogList = page.locator('[data-testid="execution-log-list"]');
    this.executionLogEntries = page.locator('[data-testid="log-entry"]');
    this.workflowHeader = page
      .locator('[data-testid="workflow-header"]')
      .or(page.locator(".workflow-header, header").first());
    this.scenarioList = page
      .locator('[data-testid="scenario-list"]')
      .or(page.locator('[data-testid="scenario"]'));
  }

  async goto() {
    await this.page.goto("/workspace/workflows");
    await this.page.waitForLoadState("domcontentloaded");
  }

  async selectScenario(name: string) {
    await this.page.locator(`text=${name}`).first().click();
  }

  async clickSaveAsTemplate() {
    // Open the Save dropdown — WorkflowHeader uses a Save+ChevronDown button
    const dropdown = this.page
      .locator(
        '[data-testid="workflow-menu"], button:has-text("Save"), button:has([class*="chevron-down"])',
      )
      .first();
    await dropdown.click();
    await this.page.locator('text=Save as Template').click();
  }

  async getLogEntryCount(): Promise<number> {
    return this.executionLogEntries.count();
  }

  async getLogEntryByType(eventType: string): Promise<Locator> {
    return this.page.locator(
      `[data-testid="log-entry"][data-event-type="${eventType}"]`,
    );
  }
}
