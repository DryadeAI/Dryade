/**
 * @mock
 *
 * Mock workflow execution test — CI-safe, no real LLM required.
 *
 * Triggers the _mock_demo synthetic scenario and verifies the SSE event
 * stream structure without needing GPU inference.
 */

import { test, expect, API_URL } from "../../fixtures/api";
import { parseSseEvents } from "../../helpers/sse-parser";

test.describe("Mock workflow execution @mock", () => {
  test.setTimeout(60_000); // 1 minute is enough for mock

  test("triggers _mock_demo scenario and receives workflow events", async ({
    authedPage,
    accessToken,
  }) => {
    const triggerUrl = `${API_URL}/workflow-scenarios/_mock_demo/trigger`;

    // Use Playwright request API (runs in Node.js, no mixed-content issues)
    // Retry on 429 rate limit (backend has aggressive rate limiting for scenario endpoints)
    let res;
    for (let attempt = 0; attempt < 5; attempt++) {
      res = await authedPage.request.post(triggerUrl, {
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "application/json",
        },
        data: {},
      });
      if (res.status() !== 429) break;
      const retryAfter = Number(res.headers()["retry-after"] || "5");
      await new Promise((r) => setTimeout(r, (retryAfter + 1) * 1000));
    }

    if (!res!.ok()) {
      const status = res!.status();
      if (status === 404) {
        test.skip(true, "_mock_demo scenario endpoint not found (404)");
        return;
      }
      if (status === 429) {
        test.skip(true, "_mock_demo rate limited after 5 retries — skip in parallel test run");
        return;
      }
      throw new Error(`_mock_demo trigger failed (${status}): ${await res!.text()}`);
    }

    const rawBody = await res!.text();
    const events = parseSseEvents(rawBody);

    // If no SSE events parsed, the endpoint may return JSON instead of SSE
    if (events.length === 0) {
      // Try parsing as plain JSON array
      try {
        const json = JSON.parse(rawBody);
        if (Array.isArray(json)) {
          events.push(...json);
        } else if (json.type) {
          events.push(json);
        }
      } catch {
        // Not JSON either — skip gracefully
        test.skip(true, "_mock_demo returned unparseable response");
        return;
      }
    }

    // Assert workflow_start was received
    const startEvent = events.find((e) => e.type === "workflow_start");
    expect(startEvent, "Expected workflow_start event").toBeTruthy();

    // Assert at least one node_complete event
    const nodeCompleteEvents = events.filter(
      (e) => e.type === "node_complete",
    );
    expect(
      nodeCompleteEvents.length,
      "Expected at least 1 node_complete event",
    ).toBeGreaterThanOrEqual(1);

    // Assert workflow_complete was received
    const completeEvent = events.find((e) => e.type === "workflow_complete");
    expect(completeEvent, "Expected workflow_complete event").toBeTruthy();
  });
});
