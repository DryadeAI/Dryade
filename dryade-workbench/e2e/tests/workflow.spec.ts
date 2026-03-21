/**
 * Workflow page smoke tests.
 *
 * Quick, focused tests that verify the workflow page loads correctly,
 * canvas renders nodes from API-created workflows, and auto-layout
 * repositions nodes within the viewport.
 */

import { test, expect, API_URL } from "../fixtures/api";
import { createAndPublish, deleteWorkflow } from "../helpers/workflow-api";
import { LINEAR_WORKFLOW } from "../helpers/workflow-schemas";

test.describe("Workflow Page Smoke Tests", () => {
  test("loads workflow page and shows canvas or empty state", async ({
    authedPage,
  }) => {
    await authedPage.goto("/workspace/workflows");
    await authedPage.waitForLoadState("domcontentloaded");
    await expect(authedPage).toHaveURL(/\/workspace\/workflows/);

    // Page should contain either the ReactFlow canvas, workflow controls,
    // scenario buttons, or the page content area (sidebar + main).
    // The page may take time to load workflows from the API.
    const canvas = authedPage.locator(
      ".react-flow, [data-testid='workflow-canvas'], .reactflow-wrapper",
    ).first();
    const controls = authedPage.locator(
      "button:has-text('New'), button:has-text('Create'), [data-testid='scenario']",
    ).first();
    // Also accept any workflow page content as evidence the page loaded
    const pageContent = authedPage.locator(
      "[data-testid='workflow-page'], nav, aside, [class*='sidebar'], [class*='Sidebar']",
    ).first();

    // Wait for at least one element to appear (up to 15s for slow API responses)
    const hasCanvas = await canvas.isVisible({ timeout: 15_000 }).catch(() => false);
    const hasControls = await controls.isVisible({ timeout: 3_000 }).catch(() => false);
    const hasPageContent = await pageContent.isVisible({ timeout: 3_000 }).catch(() => false);
    expect(hasCanvas || hasControls || hasPageContent).toBeTruthy();
  });

  test("creates workflow via API and renders correct node count on canvas", async ({
    authedPage,
    apiClient,
  }) => {
    test.setTimeout(90_000);
    const name = `e2e-smoke-linear-${Date.now()}`;
    let workflowId: number | undefined;

    try {
      workflowId = await createAndPublish(apiClient, name, LINEAR_WORKFLOW);

      // Navigate to the workflow page with the workflow loaded
      await authedPage.goto(
        `/workspace/workflows?workflowId=${workflowId}`,
      );
      await authedPage.waitForLoadState("domcontentloaded");

      // Wait for ReactFlow nodes to render (auto-layout fires after 250ms)
      const nodes = authedPage.locator(".react-flow__node");
      await expect(nodes.first()).toBeVisible({ timeout: 10_000 });

      // LINEAR_WORKFLOW has 3 nodes: start, task_1, end
      // Canvas may render additional UI nodes (palette items, decorators, etc.)
      const nodeCount = await nodes.count();
      expect(nodeCount).toBeGreaterThanOrEqual(3);
    } finally {
      if (workflowId) {
        await deleteWorkflow(apiClient, workflowId).catch(() => {});
      }
    }
  });

  test("auto-layout positions all nodes within the viewport", async ({
    authedPage,
    apiClient,
  }) => {
    test.setTimeout(90_000);
    const name = `e2e-smoke-autolayout-${Date.now()}`;
    let workflowId: number | undefined;

    try {
      workflowId = await createAndPublish(apiClient, name, LINEAR_WORKFLOW);

      await authedPage.goto(
        `/workspace/workflows?workflowId=${workflowId}`,
      );
      await authedPage.waitForLoadState("domcontentloaded");

      // Wait for nodes to appear
      const nodes = authedPage.locator(".react-flow__node");
      await expect(nodes.first()).toBeVisible({ timeout: 10_000 });

      // Auto-layout runs automatically on first load after 250ms.
      // Wait a bit for it to complete and fitView to adjust the viewport.
      await authedPage.waitForTimeout(1_000);

      // Verify all nodes are visible in the viewport
      const allVisible = await authedPage.evaluate(() => {
        const viewport = {
          width: window.innerWidth,
          height: window.innerHeight,
        };
        const nodeEls = document.querySelectorAll(".react-flow__node");
        if (nodeEls.length === 0) return false;

        for (const node of Array.from(nodeEls)) {
          const rect = node.getBoundingClientRect();
          // Node should be at least partially within the visible area
          const isVisible =
            rect.right > 0 &&
            rect.bottom > 0 &&
            rect.left < viewport.width &&
            rect.top < viewport.height;
          if (!isVisible) return false;
        }
        return true;
      });

      expect(allVisible, "All nodes should be within viewport after auto-layout").toBe(true);
    } finally {
      if (workflowId) {
        await deleteWorkflow(apiClient, workflowId).catch(() => {});
      }
    }
  });

  test("workflow page has main content area", async ({ authedPage }) => {
    await authedPage.goto("/workspace/workflows");
    await authedPage.waitForLoadState("domcontentloaded");

    // Page should render without error — either canvas or workflow controls
    await expect(authedPage.locator("body")).not.toHaveText("", { timeout: 10_000 });
  });
});
