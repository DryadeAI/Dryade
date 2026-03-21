import type { Page, Locator } from "@playwright/test";

const NAV_ITEMS: Record<string, string> = {
  chat: "/workspace/chat",
  dashboard: "/workspace/dashboard",
  agents: "/workspace/agents",
  workflows: "/workspace/workflows",
  knowledge: "/workspace/knowledge",
  "cost-tracker": "/workspace/cost-tracker",
  loops: "/workspace/loops",
  factory: "/workspace/factory",
  health: "/workspace/health",
  metrics: "/workspace/metrics",
  settings: "/workspace/settings",
  profile: "/workspace/profile",
};

export class SidebarNav {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  async navigateTo(name: keyof typeof NAV_ITEMS | string) {
    const href = NAV_ITEMS[name] ?? name;
    const slug = href.split("/").pop() ?? name;
    // Prefer data-testid selector (added in phase 216-03)
    const testIdLink = this.page.getByTestId(`sidebar-nav-${slug}-link`);
    // Fallback: href-based selector
    const hrefLink = this.page.locator(`nav a[href='${href}'], aside a[href='${href}']`).first();
    const link = await testIdLink.isVisible().catch(() => false)
      ? testIdLink
      : hrefLink;
    if (await link.isVisible()) {
      await link.click();
    } else {
      // Fallback: navigate directly
      await this.page.goto(href);
    }
    await this.page.waitForLoadState("domcontentloaded");
  }

  async isActiveLink(name: string): Promise<boolean> {
    const href = NAV_ITEMS[name] ?? name;
    const link = this.page.locator(
      `nav a[href='${href}'][aria-current], nav a[href='${href}'].active, aside a[href='${href}'][data-active]`
    ).first();
    return link.isVisible();
  }

  async getNavLinks() {
    // Prefer data-testid selectors, fallback to href-based
    const testIdLinks = await this.page.locator("[data-testid^='sidebar-nav-'][data-testid$='-link']").all();
    if (testIdLinks.length > 0) return testIdLinks;
    return this.page.locator("nav a[href*='/workspace/'], aside a[href*='/workspace/']").all();
  }
}
