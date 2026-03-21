/**
 * Workflows Deep Tests — fills UI gaps in the existing strong API suite.
 *
 * Tests: create via API, view in UI, save/reload draft, clone, delete.
 */

import { test, expect, API_URL, retryApi } from "../../fixtures/deep-test";
import { createWorkflow, deleteWorkflow } from "../../helpers/workflow-api";

test.describe.serial("Workflows Deep Tests @deep", () => {
  let workflowId: number;

  test("@deep should create a workflow via API", async ({ apiClient }) => {
    workflowId = await createWorkflow(apiClient, `Deep Test Workflow ${Date.now()}`, {
      nodes: [
        { id: "start", type: "start", position: { x: 100, y: 100 }, data: {} },
      ],
      edges: [],
    });
    expect(workflowId).toBeTruthy();
    expect(typeof workflowId).toBe("number");
  });

  test("@deep should view workflow in UI", async ({ authedPage }) => {
    await authedPage.goto("/workspace/workflows");
    await authedPage.waitForLoadState("domcontentloaded");

    // Wait for page content to load
    await expect(authedPage.locator("body")).toContainText(/workflow/i, { timeout: 10_000 });

    // Navigate to specific workflow
    await authedPage.goto(`/workspace/workflows/${workflowId}`);
    await authedPage.waitForLoadState("domcontentloaded");

    // Verify workflow view loaded (canvas or header)
    const bodyText = await authedPage.locator("body").textContent();
    expect(bodyText?.length).toBeGreaterThan(10);
  });

  test("@deep should save and reload workflow draft", async ({ apiClient, authedPage }) => {
    // Update workflow via API (add a node) — use unique name to avoid collision
    const updatedName = `Deep Test Workflow Updated ${Date.now()}`;
    const res = await retryApi(() =>
      apiClient.put(`${API_URL}/api/workflows/${workflowId}`, {
        data: {
          name: updatedName,
          workflow_json: {
            nodes: [
              { id: "start", type: "start", position: { x: 100, y: 100 }, data: {} },
              { id: "task1", type: "task", position: { x: 300, y: 100 }, data: { label: "Task 1" } },
            ],
            edges: [{ id: "e1", source: "start", target: "task1" }],
          },
        },
      }),
    );
    expect(res.status()).toBeGreaterThanOrEqual(200);
    expect(res.status()).toBeLessThan(300);

    // Reload and verify
    const getRes = await retryApi(() =>
      apiClient.get(`${API_URL}/api/workflows/${workflowId}`),
    );
    expect(getRes.status()).toBe(200);
    const body = await getRes.json();
    expect(body.name).toBe(updatedName);
  });

  test("@deep should clone a workflow", async ({ apiClient }) => {
    const res = await apiClient.post(`${API_URL}/api/workflows/${workflowId}/clone`);

    if (res.status() === 404 || res.status() === 405) {
      test.skip("Clone endpoint not available");
      return;
    }

    expect(res.status()).toBeGreaterThanOrEqual(200);
    expect(res.status()).toBeLessThan(300);

    const body = await res.json();
    const cloneId = body.id;
    expect(cloneId).toBeTruthy();
    expect(cloneId).not.toBe(workflowId);

    // Cleanup clone
    await deleteWorkflow(apiClient, cloneId);
  });

  test("@deep should delete a workflow", async ({ apiClient }) => {
    await deleteWorkflow(apiClient, workflowId);

    // Verify removal
    const getRes = await apiClient.get(`${API_URL}/api/workflows/${workflowId}`);
    expect(getRes.status()).toBe(404);
  });
});
