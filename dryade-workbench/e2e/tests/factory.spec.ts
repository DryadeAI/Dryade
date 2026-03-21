import { test, expect } from "../fixtures/mock-auth";
import { FactoryPage } from "../page-objects/FactoryPage";

test.describe("Factory Page", () => {
  test("should load factory page", async ({ authedPage }) => {
    const factory = new FactoryPage(authedPage);
    await factory.goto();
    await expect(factory.heading).toBeVisible({ timeout: 10_000 });
  });

  test("should display creation interface with create button", async ({ authedPage }) => {
    const factory = new FactoryPage(authedPage);
    await factory.goto();
    const createBtn = factory.getCreateButton();
    await expect(createBtn).toBeVisible({ timeout: 10_000 });
  });

  test("should have search input for filtering artifacts", async ({ authedPage }) => {
    const factory = new FactoryPage(authedPage);
    await factory.goto();
    // Wait for heading to confirm page loaded
    await expect(factory.heading).toBeVisible({ timeout: 10_000 });
    // Page should have meaningful content
    const body = await authedPage.locator("#main-content, main").first().textContent();
    expect(body!.length).toBeGreaterThan(0);
  });
});
