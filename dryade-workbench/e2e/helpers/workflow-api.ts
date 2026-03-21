/**
 * Workflow CRUD helper for E2E test setup/teardown.
 *
 * Wraps the /api/workflows REST API with convenience functions
 * for creating, publishing, retrieving, and deleting workflows.
 * Uses Playwright's APIRequestContext for HTTP calls.
 */

import type { APIRequestContext } from "@playwright/test";
import type { WorkflowSchemaJson } from "./workflow-schemas";

const API_PREFIX = "/api/workflows";

/** Response shape from POST /api/workflows and GET /api/workflows/:id */
export interface WorkflowResponse {
  id: number;
  name: string;
  description: string | null;
  version: string;
  workflow_json: Record<string, unknown>;
  status: string;
  is_public: boolean;
  user_id: string | null;
  tags: string[];
  execution_count: number;
  created_at: string;
  updated_at: string;
  published_at: string | null;
}

/**
 * Create a draft workflow via the API.
 * @returns The numeric workflow ID.
 */
export async function createWorkflow(
  apiClient: APIRequestContext,
  name: string,
  schema: WorkflowSchemaJson,
  options?: { description?: string; tags?: string[]; isPublic?: boolean },
): Promise<number> {
  // Retry on 429 rate limit with exponential backoff
  for (let attempt = 0; attempt < 5; attempt++) {
    const res = await apiClient.post(API_PREFIX, {
      data: {
        name,
        description: options?.description ?? `E2E test workflow: ${name}`,
        workflow_json: schema,
        tags: options?.tags ?? ["e2e-test"],
        is_public: options?.isPublic ?? false,
      },
    });

    if (res.ok()) {
      const json: WorkflowResponse = await res.json();
      return json.id;
    }

    if (res.status() === 429 && attempt < 4) {
      const retryAfter = Number(res.headers()["retry-after"] || "3");
      await new Promise((r) => setTimeout(r, (retryAfter + 1) * 1000));
      continue;
    }

    const body = await res.text();
    throw new Error(
      `createWorkflow failed (${res.status()}): ${body}`,
    );
  }
  throw new Error("createWorkflow: unreachable");
}

/**
 * Publish a draft workflow, making it executable.
 */
export async function publishWorkflow(
  apiClient: APIRequestContext,
  workflowId: number,
): Promise<void> {
  // Retry on 429 rate limit with exponential backoff
  for (let attempt = 0; attempt < 5; attempt++) {
    const res = await apiClient.post(`${API_PREFIX}/${workflowId}/publish`);

    if (res.ok()) return;

    if (res.status() === 429 && attempt < 4) {
      const retryAfter = Number(res.headers()["retry-after"] || "3");
      await new Promise((r) => setTimeout(r, (retryAfter + 1) * 1000));
      continue;
    }

    const body = await res.text();
    throw new Error(
      `publishWorkflow(${workflowId}) failed (${res.status()}): ${body}`,
    );
  }
}

/**
 * Delete a workflow (must be in draft status).
 * Silently ignores 404 (already deleted) for cleanup resilience.
 */
export async function deleteWorkflow(
  apiClient: APIRequestContext,
  workflowId: number,
): Promise<void> {
  const res = await apiClient.delete(`${API_PREFIX}/${workflowId}`);

  if (!res.ok() && res.status() !== 404) {
    const body = await res.text();
    throw new Error(
      `deleteWorkflow(${workflowId}) failed (${res.status()}): ${body}`,
    );
  }
}

/**
 * Get full workflow details by ID.
 */
export async function getWorkflow(
  apiClient: APIRequestContext,
  workflowId: number,
): Promise<WorkflowResponse> {
  const res = await apiClient.get(`${API_PREFIX}/${workflowId}`);

  if (!res.ok()) {
    const body = await res.text();
    throw new Error(
      `getWorkflow(${workflowId}) failed (${res.status()}): ${body}`,
    );
  }

  return res.json();
}

/**
 * Convenience: create a workflow and immediately publish it.
 * @returns The numeric workflow ID (now in published status).
 */
export async function createAndPublish(
  apiClient: APIRequestContext,
  name: string,
  schema: WorkflowSchemaJson,
  options?: { description?: string; tags?: string[]; isPublic?: boolean },
): Promise<number> {
  const id = await createWorkflow(apiClient, name, schema, options);
  await publishWorkflow(apiClient, id);
  return id;
}
