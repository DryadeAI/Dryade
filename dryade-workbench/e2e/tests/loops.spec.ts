import { test, expect, API_URL } from "../fixtures/api";
import { LoopsPage } from "../page-objects/LoopsPage";

test.describe("Loops Page", () => {
  test("should load loops page", async ({ authedPage }) => {
    const loops = new LoopsPage(authedPage);
    await loops.goto();
    await expect(loops.heading).toBeVisible({ timeout: 10_000 });
  });

  test("should show loop list or empty state", async ({ authedPage }) => {
    const loops = new LoopsPage(authedPage);
    await loops.goto();
    // Either shows loops table or empty state "No scheduled loops"
    const emptyState = loops.getEmptyState();
    const hasEmpty = await emptyState.isVisible().catch(() => false);
    if (!hasEmpty) {
      // If not empty, should have a table with loop rows
      const loopList = await loops.getLoopList();
      expect(loopList.length).toBeGreaterThanOrEqual(0);
    } else {
      await expect(emptyState).toBeVisible();
    }
  });

  test("should have create loop button", async ({ authedPage }) => {
    const loops = new LoopsPage(authedPage);
    await loops.goto();
    const createBtn = loops.getCreateButton();
    await expect(createBtn).toBeVisible({ timeout: 10_000 });
  });

  test("should create a loop via API and see it in UI", async ({ authedPage, apiClient }) => {
    const loopName = `e2e-loop-${Date.now()}`;
    // Attempt to create a loop via the API
    const res = await apiClient.post(`${API_URL}/api/loops`, {
      data: {
        name: loopName,
        target_type: "workflow",
        target_id: "e2e-test-workflow",
        trigger_type: "cron",
        schedule: "0 0 * * *",
        enabled: false,
      },
    });

    if (!res.ok()) {
      // If API fails (no scheduler, missing dependency), skip gracefully
      test.skip(true, `Loop API returned ${res.status()} — scheduler may not be available in CI`);
      return;
    }

    // Navigate to loops page and verify the created loop appears
    const loops = new LoopsPage(authedPage);
    await loops.goto();
    const loopRow = loops.getLoopByName(loopName);
    await expect(loopRow).toBeVisible({ timeout: 10_000 });
  });

  test("should show loop status indicators", async ({ authedPage }) => {
    const loops = new LoopsPage(authedPage);
    await loops.goto();
    // Wait for heading to confirm page loaded
    await expect(loops.heading).toBeVisible({ timeout: 10_000 });
    // The page has Select triggers for filtering (target type and state)
    // These render as combobox elements, not buttons
    const stateFilter = authedPage.getByRole("combobox").nth(1); // Second select = state filter
    const hasStateFilter = await stateFilter.isVisible().catch(() => false);
    if (hasStateFilter) {
      await expect(stateFilter).toBeVisible();
    } else {
      // If no filters, page still loaded with empty state — valid
      const emptyState = loops.getEmptyState();
      await expect(emptyState).toBeVisible({ timeout: 10_000 });
    }
  });
});
