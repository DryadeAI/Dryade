import { test, expect } from "../fixtures/mock-auth";
import { SettingsPage } from "../page-objects/SettingsPage";

/**
 * Settings page has 8 tabs across 3 groups:
 * ACCOUNT: Profile, Appearance, Notifications
 * WORKSPACE: Chat & Agents, Models, API Keys, Factory
 * ADVANCED: Data & Privacy
 *
 * The page uses a sidebar nav (not role="tab"), so we click nav buttons.
 */

// Settings uses sidebar buttons, not role="tab" — SettingsPage.clickTab uses getByRole("tab")
// which won't match. We use the button text directly.
const ALL_SETTINGS_TABS = [
  { id: "profile", label: "Profile", group: "ACCOUNT" },
  { id: "appearance", label: "Appearance", group: "ACCOUNT" },
  { id: "notifications", label: "Notifications", group: "ACCOUNT" },
  { id: "chat", label: "Chat & Agents", group: "WORKSPACE" },
  { id: "models", label: "Models", group: "WORKSPACE" },
  { id: "api-keys", label: "API Keys", group: "WORKSPACE" },
  { id: "factory", label: "Factory", group: "WORKSPACE" },
  { id: "data", label: "Data & Privacy", group: "ADVANCED" },
] as const;

test.describe("Settings Page — All Tabs", () => {
  test("should load settings with sidebar navigation", async ({ authedPage }) => {
    const settings = new SettingsPage(authedPage);
    await settings.goto();
    // Settings heading "Settings" (h2) in the right sidebar panel
    const settingsHeading = authedPage.getByRole("heading", { name: "Settings" });
    await expect(settingsHeading).toBeVisible({ timeout: 10_000 });
    // Wait for the settings nav to render — look for "Profile" button
    // which is the first settings tab button (inside the settings nav, not sidebar)
    const profileBtn = authedPage.getByRole("button", { name: "Profile" });
    await expect(profileBtn).toBeVisible({ timeout: 10_000 });
    // Verify multiple settings tab buttons exist by checking known tabs
    for (const tab of ["Profile", "Appearance", "Models", "Data & Privacy"]) {
      await expect(authedPage.getByRole("button", { name: tab })).toBeVisible();
    }
  });

  test("should have search settings input", async ({ authedPage }) => {
    const settings = new SettingsPage(authedPage);
    await settings.goto();
    const searchInput = authedPage.getByLabel("Search settings");
    await expect(searchInput).toBeVisible({ timeout: 10_000 });
  });

  test("should display all 3 group headers", async ({ authedPage }) => {
    const settings = new SettingsPage(authedPage);
    await settings.goto();
    for (const group of ["ACCOUNT", "WORKSPACE", "ADVANCED"]) {
      const groupHeader = authedPage.getByText(group, { exact: true }).first();
      await expect(groupHeader).toBeVisible({ timeout: 5_000 });
    }
  });

  for (const tab of ALL_SETTINGS_TABS) {
    test(`should switch to ${tab.label} tab and show content`, async ({ authedPage }) => {
      const settings = new SettingsPage(authedPage);
      await settings.goto();
      // Click the nav button for this tab
      const navBtn = authedPage.locator("nav button").filter({ hasText: tab.label }).first();
      await expect(navBtn).toBeVisible({ timeout: 10_000 });
      await navBtn.click();
      // Wait for content to update
      await authedPage.waitForTimeout(300);
      // The active section heading (h1) should show the tab label
      const heading = authedPage.locator("h1").first();
      await expect(heading).toBeVisible({ timeout: 5_000 });
      const headingText = await heading.textContent();
      expect(headingText!.toLowerCase()).toContain(tab.label.toLowerCase().split(" ")[0]);
    });
  }

  test("Profile tab should show user email and display name fields", async ({ authedPage }) => {
    const settings = new SettingsPage(authedPage);
    await settings.goto();
    // Profile is the default tab — the h1 should show "Profile"
    const heading = authedPage.locator("h1").first();
    await expect(heading).toBeVisible({ timeout: 10_000 });
    const headingText = await heading.textContent();
    expect(headingText).toMatch(/profile/i);
    // Content panel (left side, .flex-1 > .max-w-2xl) should have profile-related fields
    const content = authedPage.locator(".max-w-2xl").first();
    const text = await content.textContent();
    expect(text).toMatch(/email|display.?name|profile/i);
  });

  test("Appearance tab should have theme controls", async ({ authedPage }) => {
    const settings = new SettingsPage(authedPage);
    await settings.goto();
    const navBtn = authedPage.locator("nav button").filter({ hasText: "Appearance" }).first();
    await navBtn.click();
    await authedPage.waitForTimeout(300);
    // The h1 should update to "Appearance"
    const heading = authedPage.locator("h1").first();
    await expect(heading).toContainText(/appearance/i, { timeout: 5_000 });
    // Content panel should have theme-related controls
    const content = authedPage.locator(".max-w-2xl").first();
    const text = await content.textContent();
    expect(text).toMatch(/theme|dark|light|font|compact/i);
  });

  test("Models tab should show provider configuration", async ({ authedPage }) => {
    const settings = new SettingsPage(authedPage);
    await settings.goto();
    const navBtn = authedPage.locator("nav button").filter({ hasText: "Models" }).first();
    await navBtn.click();
    await authedPage.waitForTimeout(500);
    // The h1 should update to "Models"
    const heading = authedPage.locator("h1").first();
    await expect(heading).toContainText(/model/i, { timeout: 5_000 });
    // Content panel should have model/provider related content
    const content = authedPage.locator(".max-w-2xl").first();
    const text = await content.textContent();
    expect(text).toMatch(/provider|model|llm|embedding|audio/i);
  });

  test("Data & Privacy tab should show auto-save and data management", async ({ authedPage }) => {
    const settings = new SettingsPage(authedPage);
    await settings.goto();
    const navBtn = authedPage.locator("nav button").filter({ hasText: "Data" }).first();
    await navBtn.click();
    await authedPage.waitForTimeout(300);
    const heading = authedPage.locator("h1").first();
    await expect(heading).toContainText(/data|privacy/i, { timeout: 5_000 });
    const content = authedPage.locator(".max-w-2xl").first();
    const text = await content.textContent();
    expect(text).toMatch(/auto.?save|data|privacy|export|account/i);
  });

  test("search settings should filter nav items", async ({ authedPage }) => {
    const settings = new SettingsPage(authedPage);
    await settings.goto();
    const searchInput = authedPage.getByLabel("Search settings");
    await expect(searchInput).toBeVisible({ timeout: 10_000 });
    await searchInput.fill("model");
    await authedPage.waitForTimeout(500);
    // Only matching items should be visible
    const modelsBtn = authedPage.locator("nav button").filter({ hasText: "Models" }).first();
    await expect(modelsBtn).toBeVisible({ timeout: 5_000 });
    // Non-matching items should be hidden or reduced
    const navButtons = await authedPage.locator("nav button").all();
    // Filter should reduce visible nav items
    const visibleCount = (await Promise.all(navButtons.map(b => b.isVisible()))).filter(Boolean).length;
    expect(visibleCount).toBeLessThan(8); // Less than all 8 tabs
  });
});
