/**
 * Auto-approve polling helper for approval node E2E tests.
 *
 * Provides two strategies:
 * 1. autoApproveAfterDelay - wait, then approve all pending approvals
 * 2. pollAndAutoApprove - poll in a loop until approvals appear, then approve
 *
 * Both use the /api/workflows REST API for approval management.
 * The approval endpoints are workflow-scoped:
 *   GET  /api/workflows/{workflowId}/approvals/pending
 *   POST /api/workflows/{workflowId}/approvals/{requestId}/action
 */

import type { APIRequestContext } from "@playwright/test";

const API_PREFIX = "/api/workflows";

interface ApprovalRequest {
  id: number;
  workflow_id: number;
  node_id: string;
  prompt: string;
  approver_type: string;
  status: string;
}

/**
 * Wait a fixed delay, then approve all pending approvals for a workflow.
 *
 * Best used when you know an approval will be pending shortly (e.g.,
 * run this concurrently with workflow execution via Promise.all).
 *
 * @returns Number of approvals processed.
 */
export async function autoApproveAfterDelay(
  apiClient: APIRequestContext,
  workflowId: number,
  delayMs = 2000,
): Promise<number> {
  await new Promise((resolve) => setTimeout(resolve, delayMs));

  const res = await apiClient.get(
    `${API_PREFIX}/${workflowId}/approvals/pending`,
  );

  if (!res.ok()) {
    // No pending approvals or endpoint error -- not fatal in tests
    return 0;
  }

  const pending: ApprovalRequest[] = await res.json();
  let approved = 0;

  for (const approval of pending) {
    const actionRes = await apiClient.post(
      `${API_PREFIX}/${workflowId}/approvals/${approval.id}/action`,
      {
        data: { action: "approve", modified_fields: null },
      },
    );

    if (actionRes.ok()) {
      approved++;
    }
  }

  return approved;
}

interface PollResult {
  approved: boolean;
  attempts: number;
}

/**
 * Poll for pending approvals and approve immediately when found.
 *
 * Best used when the timing of the approval pause is uncertain.
 * Polls every `intervalMs` up to `maxAttempts` times.
 *
 * @returns Whether an approval was processed and how many poll cycles ran.
 */
export async function pollAndAutoApprove(
  apiClient: APIRequestContext,
  workflowId: number,
  maxAttempts = 10,
  intervalMs = 1000,
): Promise<PollResult> {
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const res = await apiClient.get(
      `${API_PREFIX}/${workflowId}/approvals/pending`,
    );

    if (res.ok()) {
      const pending: ApprovalRequest[] = await res.json();

      if (pending.length > 0) {
        for (const approval of pending) {
          await apiClient.post(
            `${API_PREFIX}/${workflowId}/approvals/${approval.id}/action`,
            {
              data: { action: "approve", modified_fields: null },
            },
          );
        }
        return { approved: true, attempts: attempt };
      }
    }

    if (attempt < maxAttempts) {
      await new Promise((resolve) => setTimeout(resolve, intervalMs));
    }
  }

  return { approved: false, attempts: maxAttempts };
}
