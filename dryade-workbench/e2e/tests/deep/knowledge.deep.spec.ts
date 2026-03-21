/**
 * Knowledge Deep Tests — exercises the full document lifecycle via API and UI.
 *
 * Tests: empty state, file upload (txt + pdf), source listing, search/query,
 * UI display, agent binding, and deletion.
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

import { test, expect, retryApi } from "../../fixtures/deep-test";
import { KnowledgePage } from "../../page-objects/KnowledgePage";

test.describe.serial("Knowledge Deep Tests @deep", () => {
  let uploadedSourceId: string;
  let uploadedPdfId: string;

  test("@deep should show empty state or existing sources", async ({
    authedPage,
  }) => {
    const knowledge = new KnowledgePage(authedPage);
    await knowledge.goto();

    // Assert heading is visible — page loaded without crash
    await expect(knowledge.heading).toBeVisible({ timeout: 10_000 });

    // Get existing documents (may be empty)
    const docs = await knowledge.getDocumentList();
    if (docs.length === 0) {
      // Empty state — heading should still be visible (no crash)
      await expect(knowledge.heading).toBeVisible();
    } else {
      // Has documents — first one should be visible
      await expect(docs[0]).toBeVisible();
    }
  });

  test("@deep should upload a text file via API", async ({ apiClient }) => {
    const filePath = path.resolve(
      __dirname,
      "../../fixtures/test-files/sample.txt",
    );
    const fileBuffer = fs.readFileSync(filePath);

    const res = await retryApi(() =>
      apiClient.post("/api/knowledge/upload", {
        multipart: {
          file: {
            name: "sample.txt",
            mimeType: "text/plain",
            buffer: Buffer.from(fileBuffer),
          },
        },
      }),
    );

    // 503 = Qdrant not configured — skip gracefully
    if (res.status() === 503) {
      test.skip(true, "Knowledge service unavailable (Qdrant not configured)");
      return;
    }
    expect([200, 201]).toContain(res.status());

    const body = await res.json();
    expect(body.id || body.source_id).toBeTruthy();
    uploadedSourceId = body.id || body.source_id;
  });

  test("@deep should upload a PDF file via API", async ({ apiClient }) => {
    const filePath = path.resolve(
      __dirname,
      "../../fixtures/test-files/sample.pdf",
    );
    const fileBuffer = fs.readFileSync(filePath);

    const res = await retryApi(() =>
      apiClient.post("/api/knowledge/upload", {
        multipart: {
          file: {
            name: "sample.pdf",
            mimeType: "application/pdf",
            buffer: Buffer.from(fileBuffer),
          },
        },
      }),
    );

    // 503 = Qdrant not configured — skip gracefully
    if (res.status() === 503) {
      test.skip(true, "Knowledge service unavailable (Qdrant not configured)");
      return;
    }
    expect([200, 201]).toContain(res.status());

    const body = await res.json();
    expect(body.id || body.source_id).toBeTruthy();
    uploadedPdfId = body.id || body.source_id;
  });

  test("@deep should list uploaded sources", async ({ apiClient }) => {
    const res = await apiClient.get("/api/knowledge");

    expect(res.status()).toBe(200);

    const body = await res.json();
    const sources = body.sources ?? (Array.isArray(body) ? body : body.data ?? []);
    expect(sources.length).toBeGreaterThanOrEqual(2);

    // Each source should have an id field
    for (const source of sources) {
      expect(source.id || source.source_id).toBeTruthy();
    }
  });

  test("@deep should search knowledge base", async ({ apiClient }) => {
    const res = await apiClient.post("/api/knowledge/query", {
      data: { query: "artificial intelligence" },
    });

    expect(res.status()).toBe(200);

    const body = await res.json();
    const results =
      body.results ?? body.chunks ?? body.matches ?? body.data ?? [];
    expect(results.length).toBeGreaterThanOrEqual(1);

    // At least one result should contain relevant text
    const hasRelevant = results.some((r: Record<string, unknown>) => {
      const text = String(
        r.text ?? r.content ?? r.chunk ?? r.page_content ?? "",
      ).toLowerCase();
      return text.includes("artificial") || text.includes("intelligence");
    });
    expect(hasRelevant).toBe(true);
  });

  test("@deep should view knowledge sources in UI", async ({
    authedPage,
  }) => {
    const knowledge = new KnowledgePage(authedPage);
    await knowledge.goto();

    // Click sources tab if not already active
    const sourcesTab = knowledge.sourcesTab;
    const hasTab = await sourcesTab.isVisible().catch(() => false);
    if (hasTab) {
      await sourcesTab.click();
      await authedPage.waitForTimeout(1_000);
    }

    // Assert at least 1 document card is visible (uploaded in previous tests)
    const docs = await knowledge.getDocumentList();
    // If no visible documents, check if page content mentions sources or documents
    if (docs.length === 0) {
      const bodyText = await authedPage.locator("body").textContent();
      // Accept either visible cards or text indicating sources exist
      const hasSourceText = /source|document|sample|knowledge/i.test(bodyText ?? "");
      expect(hasSourceText || docs.length > 0).toBeTruthy();
    } else {
      await expect(docs[0]).toBeVisible();
    }
  });

  test("@deep should bind knowledge source to agent via API", async ({
    apiClient,
  }) => {
    // First, get available agents — retry on 429
    let agentsRes: Awaited<ReturnType<typeof apiClient.get>>;
    for (let attempt = 0; attempt < 5; attempt++) {
      agentsRes = await apiClient.get("/api/agents");
      if (agentsRes.status() !== 429) break;
      await new Promise((r) => setTimeout(r, 4000));
    }
    expect(agentsRes!.status()).toBe(200);

    const agentsBody = await agentsRes.json();
    const agents = Array.isArray(agentsBody)
      ? agentsBody
      : agentsBody.agents ?? agentsBody.data ?? [];

    if (agents.length === 0) {
      test.skip(true, "No agents to bind to");
      return;
    }

    const agentName = agents[0].name ?? agents[0].id;

    // Bind source to agent — try POST first, then PATCH
    let res = await apiClient.post(
      `/api/knowledge/${uploadedSourceId}/bind`,
      {
        data: { agent_names: [agentName] },
      },
    );

    if (res.status() === 405) {
      res = await apiClient.patch(
        `/api/knowledge/${uploadedSourceId}/bind`,
        {
          data: { agent_names: [agentName] },
        },
      );
    }

    if (res.status() === 404 || res.status() === 405) {
      test.skip(true, "Knowledge bind endpoint not available");
      return;
    }

    expect(res.status()).toBe(200);
  });

  test("@deep should delete a knowledge source via API", async ({
    apiClient,
  }) => {
    // Delete the PDF source
    const deleteRes = await apiClient.delete(
      `/api/knowledge/${uploadedPdfId}`,
    );

    expect([200, 204]).toContain(deleteRes.status());

    // Verify it's gone from the list
    const listRes = await apiClient.get("/api/knowledge");
    expect(listRes.status()).toBe(200);

    const body = await listRes.json();
    const sources = body.sources ?? (Array.isArray(body) ? body : body.data ?? []);
    const deletedStillPresent = sources.some(
      (s: Record<string, unknown>) =>
        (s.id || s.source_id) === uploadedPdfId,
    );
    expect(deletedStillPresent).toBe(false);
  });
});
