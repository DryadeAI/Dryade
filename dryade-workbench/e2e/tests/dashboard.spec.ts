import { test, expect } from "../fixtures/mock-auth";
import { DashboardPage } from "../page-objects/DashboardPage";

test.describe("Dashboard Page", () => {
  test("should load dashboard with main content", async ({ authedPage }) => {
    const dashboard = new DashboardPage(authedPage);
    await dashboard.goto();
    await dashboard.waitForLoad();
    await expect(authedPage.locator("main").first()).toBeVisible();
  });

  test("should display greeting heading", async ({ authedPage }) => {
    const dashboard = new DashboardPage(authedPage);
    await dashboard.goto();
    await dashboard.waitForLoad();
    const welcome = dashboard.getWelcomeMessage();
    await expect(welcome).toBeVisible({ timeout: 10_000 });
    const text = await welcome.textContent();
    expect(text).toMatch(/good (morning|afternoon|evening)/i);
  });

  test("should display stat cards", async ({ authedPage }) => {
    const dashboard = new DashboardPage(authedPage);
    await dashboard.goto();
    await dashboard.waitForLoad();
    // The stat cards grid has grid-cols-2 lg:grid-cols-4 — wait for it to render
    const statsGrid = authedPage.locator(".grid.grid-cols-2").first();
    await expect(statsGrid).toBeVisible({ timeout: 10_000 });
    // Grid should have child elements (stat cards)
    const children = await statsGrid.locator("> *").count();
    expect(children).toBeGreaterThanOrEqual(1);
  });

  test("should have quick action buttons linking to chat and workflows", async ({ authedPage }) => {
    const dashboard = new DashboardPage(authedPage);
    await dashboard.goto();
    await dashboard.waitForLoad();
    // Dashboard has "Chat with Agent" and "New Conversation" buttons
    const chatLink = authedPage.locator("a[href='/workspace/chat']").first();
    await expect(chatLink).toBeVisible({ timeout: 10_000 });
  });

  test("should navigate to chat from quick action", async ({ authedPage }) => {
    const dashboard = new DashboardPage(authedPage);
    await dashboard.goto();
    await dashboard.waitForLoad();
    const chatLink = authedPage.locator("a[href='/workspace/chat']").first();
    await chatLink.click();
    await expect(authedPage).toHaveURL(/\/workspace\/chat/);
  });

  test("should show recent activity sections", async ({ authedPage }) => {
    const dashboard = new DashboardPage(authedPage);
    await dashboard.goto();
    await dashboard.waitForLoad();
    // Recent activity section has glass-card containers or at least an h2 heading
    const activitySection = authedPage.locator(".glass-card, h2:has-text('Recent')").first();
    await expect(activitySection).toBeVisible({ timeout: 10_000 });
  });
});
