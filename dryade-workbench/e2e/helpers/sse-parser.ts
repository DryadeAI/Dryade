/**
 * SSE parser utilities for workflow execution event streams.
 *
 * Provides typed event parsing and stream consumption for:
 * - POST /workflow-scenarios/{name}/trigger (scenario endpoint)
 * - POST /api/workflows/{id}/execute (workflow execute endpoint)
 *
 * The two endpoints use different event type names:
 * - Scenario: workflow_start, workflow_complete
 * - Execute:  start, complete
 * Both share: node_start, node_complete, error, approval_pending
 */

export interface ExecutionEvent {
  type:
    | "workflow_start"
    | "node_start"
    | "node_complete"
    | "checkpoint"
    | "error"
    | "workflow_complete"
    | "approval_pending"
    | "start"
    | "complete";
  execution_id?: string;
  scenario_name?: string;
  node_id?: string;
  node_type?: string;
  data?: unknown;
  result?: unknown;
  output?: unknown;
  timestamp?: string;
  error?: string;
  prompt?: string;
  approver?: string;
  workflow_id?: number;
  workflow_name?: string;
  duration_ms?: number;
  approval_request_id?: number;
}

/**
 * Parse raw SSE body text into typed events.
 * SSE format: 'data: {json}\n\n' per event.
 */
export function parseSseEvents(rawBody: string): ExecutionEvent[] {
  const events: ExecutionEvent[] = [];
  const blocks = rawBody.split("\n\n").filter(Boolean);
  for (const block of blocks) {
    const dataLine = block.split("\n").find((l) => l.startsWith("data: "));
    if (!dataLine) continue;
    try {
      const payload = JSON.parse(dataLine.slice(6));
      events.push(payload as ExecutionEvent);
    } catch {
      // Malformed line - skip
    }
  }
  return events;
}

/**
 * Consume SSE stream via Playwright request API (Node.js context).
 * Returns all events collected until workflow_complete or error or timeout.
 *
 * Uses page.request.post() to avoid mixed-content issues when the
 * frontend runs on HTTPS and the API runs on HTTP.
 */
export async function consumeSseStream(
  page: import("@playwright/test").Page,
  url: string,
  accessToken: string,
  inputs: Record<string, unknown> = {},
  timeoutMs = 300_000,
): Promise<ExecutionEvent[]> {
  const res = await page.request.post(url, {
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
      Accept: "text/event-stream",
    },
    data: inputs,
    timeout: timeoutMs,
  });

  const rawBody = await res.text();
  return parseSseEvents(rawBody);
}
