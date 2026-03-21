import { test, expect } from "../fixtures/mock-auth";
import { KnowledgePage } from "../page-objects/KnowledgePage";

test.describe("Knowledge Base Page", () => {
  test("should load knowledge page", async ({ authedPage }) => {
    const knowledge = new KnowledgePage(authedPage);
    await knowledge.goto();
    await expect(knowledge.heading).toBeVisible({ timeout: 10_000 });
  });

  test("should show document list or empty state", async ({ authedPage }) => {
    const knowledge = new KnowledgePage(authedPage);
    await knowledge.goto();
    // Wait for heading to confirm page loaded
    await expect(knowledge.heading).toBeVisible({ timeout: 10_000 });
    // Either has documents or shows sources tab
    const sourcesTab = knowledge.sourcesTab;
    const hasTab = await sourcesTab.isVisible().catch(() => false);
    if (hasTab) {
      await sourcesTab.click();
    }
    // Page should have content (documents or empty message)
    const body = await authedPage.locator("#main-content, main").first().textContent();
    expect(body!.length).toBeGreaterThan(0);
  });

  test("should have upload tab", async ({ authedPage }) => {
    const knowledge = new KnowledgePage(authedPage);
    await knowledge.goto();
    const uploadBtn = knowledge.getUploadButton();
    await expect(uploadBtn).toBeVisible({ timeout: 10_000 });
  });

  test("should have search button", async ({ authedPage }) => {
    const knowledge = new KnowledgePage(authedPage);
    await knowledge.goto();
    const searchBtn = knowledge.getSearchButton();
    await expect(searchBtn).toBeVisible({ timeout: 10_000 });
  });

  test("should handle empty knowledge base gracefully", async ({ authedPage }) => {
    const knowledge = new KnowledgePage(authedPage);
    await knowledge.goto();
    // Page should not crash — should show structured content
    await expect(authedPage.locator("body")).not.toHaveText("", { timeout: 5_000 });
  });
});
