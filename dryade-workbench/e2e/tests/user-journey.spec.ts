import { test, expect } from "../fixtures/mock-auth";
import { DashboardPage } from "../page-objects/DashboardPage";
import { AgentsPage } from "../page-objects/AgentsPage";
import { ChatPage } from "../page-objects/ChatPage";
import { SidebarNav } from "../page-objects/SidebarNav";
import { SettingsPage } from "../page-objects/SettingsPage";
import { HealthPage } from "../page-objects/HealthPage";
import { MetricsPage } from "../page-objects/MetricsPage";
import { CostTrackerPage } from "../page-objects/CostTrackerPage";
import { KnowledgePage } from "../page-objects/KnowledgePage";

test.describe("User Journeys", () => {
  test("new user onboarding: dashboard -> agents -> chat", async ({ authedPage }) => {
    // Land on dashboard
    const dashboard = new DashboardPage(authedPage);
    await dashboard.waitForLoad();
    await expect(authedPage.locator("main").first()).toBeVisible();

    // Navigate to agents
    const sidebar = new SidebarNav(authedPage);
    await sidebar.navigateTo("agents");
    await expect(authedPage).toHaveURL(/\/workspace\/agents/);
    const agents = new AgentsPage(authedPage);
    await expect(agents.heading).toBeVisible({ timeout: 10_000 });

    // Navigate to chat
    await sidebar.navigateTo("chat");
    await expect(authedPage).toHaveURL(/\/workspace\/chat/);
    const chat = new ChatPage(authedPage);
    await expect(chat.messageInput).toBeVisible({ timeout: 10_000 });
  });

  test("configure then use: settings -> chat -> verify", async ({ authedPage }) => {
    const sidebar = new SidebarNav(authedPage);

    // Navigate to settings
    await sidebar.navigateTo("settings");
    await expect(authedPage).toHaveURL(/\/workspace\/settings/);
    const settings = new SettingsPage(authedPage);
    // Click Appearance tab
    const appearanceBtn = authedPage.locator("nav button").filter({ hasText: "Appearance" }).first();
    if (await appearanceBtn.isVisible().catch(() => false)) {
      await appearanceBtn.click();
      await authedPage.waitForTimeout(300);
    }

    // Navigate to chat — verify settings didn't break the session
    await sidebar.navigateTo("chat");
    await expect(authedPage).toHaveURL(/\/workspace\/chat/);
    const chat = new ChatPage(authedPage);
    await expect(chat.messageInput).toBeVisible({ timeout: 10_000 });
    await chat.messageInput.fill("Settings test message");
    const value = await chat.messageInput.inputValue();
    expect(value).toBe("Settings test message");
  });

  test("content management: knowledge -> dashboard -> chat", async ({ authedPage }) => {
    const sidebar = new SidebarNav(authedPage);

    // Knowledge base
    await sidebar.navigateTo("knowledge");
    await expect(authedPage).toHaveURL(/\/workspace\/knowledge/);
    const knowledge = new KnowledgePage(authedPage);
    await expect(knowledge.heading).toBeVisible({ timeout: 10_000 });

    // Back to dashboard
    await sidebar.navigateTo("dashboard");
    await expect(authedPage).toHaveURL(/\/workspace\/dashboard/);
    const dashboard = new DashboardPage(authedPage);
    await dashboard.waitForLoad();

    // To chat
    await sidebar.navigateTo("chat");
    await expect(authedPage).toHaveURL(/\/workspace\/chat/);
  });

  test("monitoring journey: health -> metrics -> cost tracker", async ({ authedPage }) => {
    const sidebar = new SidebarNav(authedPage);

    // Health
    await sidebar.navigateTo("health");
    await expect(authedPage).toHaveURL(/\/workspace\/health/);
    const health = new HealthPage(authedPage);
    await expect(health.heading).toBeVisible({ timeout: 10_000 });

    // Metrics
    await sidebar.navigateTo("metrics");
    await expect(authedPage).toHaveURL(/\/workspace\/metrics/);
    const metrics = new MetricsPage(authedPage);
    await expect(metrics.heading).toBeVisible({ timeout: 10_000 });

    // Cost tracker
    await sidebar.navigateTo("cost-tracker");
    await expect(authedPage).toHaveURL(/\/workspace\/cost-tracker/);
    const costTracker = new CostTrackerPage(authedPage);
    await expect(costTracker.heading).toBeVisible({ timeout: 10_000 });
  });

  test("full sidebar tour: visit every community page", async ({ authedPage }) => {
    const sidebar = new SidebarNav(authedPage);
    const errors: string[] = [];

    // Capture page errors
    authedPage.on("pageerror", (err) => {
      errors.push(err.message);
    });

    const routes = [
      "dashboard", "chat", "agents", "workflows", "knowledge",
      "cost-tracker", "loops", "factory", "health", "metrics", "settings",
    ];

    for (const route of routes) {
      await sidebar.navigateTo(route);
      await expect(authedPage).toHaveURL(new RegExp(`/workspace/${route}`), { timeout: 10_000 });
      // Verify not blank
      const text = await authedPage.locator("body").textContent();
      expect(text!.length).toBeGreaterThan(0);
    }

    // Report any JS errors (non-fatal for test, but useful for debugging)
    if (errors.length > 0) {
      console.warn(`Page errors during sidebar tour: ${errors.join(", ")}`);
    }
  });
});
