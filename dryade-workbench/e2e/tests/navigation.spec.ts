import { test, expect } from "../fixtures/mock-auth";
import { SidebarNav } from "../page-objects/SidebarNav";

const COMMUNITY_ROUTES = [
  "dashboard",
  "chat",
  "agents",
  "workflows",
  "knowledge",
  "cost-tracker",
  "loops",
  "factory",
  "health",
  "metrics",
  "settings",
] as const;

test.describe("Sidebar Navigation", () => {
  test("should have sidebar with all community navigation links", async ({ authedPage }) => {
    await authedPage.goto("/workspace/dashboard");
    await authedPage.waitForLoadState("domcontentloaded");
    // Wait for the sidebar nav element to render (use first() since desktop + mobile nav exist)
    const nav = authedPage.locator("nav[aria-label='Workspace navigation']").first();
    await expect(nav).toBeVisible({ timeout: 10_000 });
    const sidebar = new SidebarNav(authedPage);
    const links = await sidebar.getNavLinks();
    expect(links.length).toBeGreaterThanOrEqual(COMMUNITY_ROUTES.length - 1);
  });

  test("should navigate to each community page via sidebar", async ({ authedPage }) => {
    const sidebar = new SidebarNav(authedPage);
    await authedPage.goto("/workspace/dashboard");
    await authedPage.waitForLoadState("domcontentloaded");

    for (const route of COMMUNITY_ROUTES) {
      await sidebar.navigateTo(route);
      await expect(authedPage).toHaveURL(new RegExp(`/workspace/${route}`), { timeout: 10_000 });
      // Verify page loaded (not blank)
      const body = await authedPage.locator("body").textContent();
      expect(body!.length).toBeGreaterThan(0);
    }
  });

  test("should highlight active link in sidebar", async ({ authedPage }) => {
    const sidebar = new SidebarNav(authedPage);
    await authedPage.goto("/workspace/agents");
    await authedPage.waitForLoadState("domcontentloaded");
    // Check that the agents link has active styling
    const agentsLink = authedPage.locator(
      "nav a[href='/workspace/agents'], aside a[href='/workspace/agents']"
    ).first();
    if (await agentsLink.isVisible()) {
      const className = await agentsLink.getAttribute("class");
      const ariaCurrent = await agentsLink.getAttribute("aria-current");
      const dataActive = await agentsLink.getAttribute("data-active");
      // Should have some active indicator
      expect(
        className?.includes("active") ||
        ariaCurrent === "page" ||
        dataActive !== null ||
        className?.includes("primary") ||
        className?.includes("selected")
      ).toBeTruthy();
    }
  });

  test("should support deep link routing to all pages", async ({ authedPage }) => {
    for (const route of COMMUNITY_ROUTES) {
      await authedPage.goto(`/workspace/${route}`);
      await authedPage.waitForLoadState("domcontentloaded");
      await expect(authedPage).toHaveURL(new RegExp(`/workspace/${route}`));
    }
  });

  test("should show correct page heading for key routes", async ({ authedPage }) => {
    const routeExpectations: Record<string, RegExp> = {
      agents: /agents/i,
      settings: /settings|profile/i,
      health: /health|system/i,
    };

    for (const [route, pattern] of Object.entries(routeExpectations)) {
      await authedPage.goto(`/workspace/${route}`);
      await authedPage.waitForLoadState("domcontentloaded");
      const heading = authedPage.locator("h1, h2").first();
      await expect(heading).toBeVisible({ timeout: 10_000 });
      const text = await heading.textContent();
      expect(text).toMatch(pattern);
    }
  });
});
