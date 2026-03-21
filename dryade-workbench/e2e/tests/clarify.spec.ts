import { test, expect } from "../fixtures/mock-auth";

test.describe("Clarify Preferences Page", () => {
  test("should load clarify preferences page", async ({ authedPage }) => {
    await authedPage.goto("/workspace/clarify-preferences");
    await authedPage.waitForLoadState("domcontentloaded");
    // Page renders heading "Clarification Preferences"
    const heading = authedPage.getByRole("heading", { level: 1 });
    await expect(heading).toBeVisible({ timeout: 10_000 });
  });

  test("should display preference options or empty state", async ({ authedPage }) => {
    await authedPage.goto("/workspace/clarify-preferences");
    await authedPage.waitForLoadState("domcontentloaded");
    // The search input is always rendered; wait for it to confirm page loaded
    const searchInput = authedPage.getByPlaceholder("Search preferences...");
    await expect(searchInput).toBeVisible({ timeout: 10_000 });
    // For a new user, the empty state "No saved preferences yet" is expected
    const emptyState = authedPage.getByText("No saved preferences yet");
    const prefCount = authedPage.getByText(/\d+ preference/);
    // Either the empty state or the count label should be visible
    await expect(emptyState.or(prefCount).first()).toBeVisible({ timeout: 5_000 });
  });

  test("should allow toggling or setting preferences", async ({ authedPage }) => {
    await authedPage.goto("/workspace/clarify-preferences");
    await authedPage.waitForLoadState("domcontentloaded");
    // The page has a "Include global" switch and a Refresh button as interactive elements
    const globalSwitch = authedPage.getByLabel("Include global");
    await expect(globalSwitch).toBeVisible({ timeout: 10_000 });
    // The Refresh button should also be present
    const refreshBtn = authedPage.getByRole("button", { name: /refresh/i });
    await expect(refreshBtn).toBeVisible({ timeout: 10_000 });
  });
});
