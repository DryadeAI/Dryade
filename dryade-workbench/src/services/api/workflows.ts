// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// Workflows, Scenarios & Executions API

import { fetchWithAuth, fetchStream, getTokens } from '../apiClient';
import type {
  ScenarioInfo,
  ScenarioDetail,
  ScenarioWorkflowGraph,
  ScenarioCheckpoint,
} from '@/types/extended-api';
import type { ExecutionSummary, ExecutionDetail } from '@/types/execution';
import type { WorkflowListItem } from '@/types/workflow';

// Re-export for backward compatibility
export type { WorkflowListItem };

// Backend workflow types (GAP-040, GAP-041, GAP-042, GAP-043)
interface WorkflowNodeBackend {
  id: string;
  type: 'start' | 'task' | 'router' | 'tool' | 'end'; // GAP-040: correct types
  label: string;
  description?: string;
  agent?: string;
  task?: string;
  position: { x: number; y: number };
}

interface WorkflowEdgeBackend {
  id: string;
  source: string; // GAP-042: source/target not from/to
  target: string;
  label?: string;
  condition?: string;
}

export interface WorkflowBackendResponse {
  id: number; // GAP-041: int not string
  name: string;
  description?: string;
  version: string; // GAP-046: semver string
  status: 'draft' | 'published' | 'archived';
  is_public: boolean; // GAP-045
  user_id?: string;
  tags?: string[]; // GAP-045
  execution_count?: number; // GAP-045
  published_at?: string; // GAP-050
  created_at: string;
  updated_at: string;
  workflow_json: { // GAP-043: nested structure
    nodes: WorkflowNodeBackend[];
    edges: WorkflowEdgeBackend[];
    version: string;
    metadata?: Record<string, unknown>;
  };
}

// Workflows API (Visual Editor) - Real backend calls
export const workflowsApi = {
  getWorkflows: async (params?: {
    status?: string;
    is_public?: boolean;
  }): Promise<{ workflows: WorkflowListItem[]; total: number }> => {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set('status', params.status);
    if (params?.is_public !== undefined) searchParams.set('is_public', String(params.is_public));
    const query = searchParams.toString();

    const response = await fetchWithAuth<{ items: WorkflowListItem[]; total: number }>(
      `/workflows${query ? `?${query}` : ''}`
    );

    return {
      workflows: Array.isArray(response?.items) ? response.items : [],
      total: response?.total ?? 0,
    };
  },

  getWorkflow: async (id: number): Promise<WorkflowBackendResponse> => {
    return fetchWithAuth<WorkflowBackendResponse>(`/workflows/${id}`);
  },

  createWorkflow: async (data: {
    name: string;
    description?: string;
    workflow_json?: {
      nodes: WorkflowNodeBackend[];
      edges: WorkflowEdgeBackend[];
    };
  }): Promise<WorkflowBackendResponse> => {
    return fetchWithAuth<WorkflowBackendResponse>('/workflows', {
      method: 'POST',
      body: JSON.stringify({
        name: data.name,
        description: data.description,
        workflow_json: data.workflow_json || {
          nodes: [
            { id: 'start', type: 'start', label: 'Start', position: { x: 100, y: 200 } },
            { id: 'end', type: 'end', label: 'End', position: { x: 500, y: 200 } },
          ],
          edges: [],
          version: '1.0.0',
        },
      }),
    });
  },

  updateWorkflow: async (
    id: number,
    data: Partial<{
      name: string;
      description: string;
      workflow_json: {
        nodes: WorkflowNodeBackend[];
        edges: WorkflowEdgeBackend[];
      };
    }>
  ): Promise<WorkflowBackendResponse> => {
    // GAP-044 FIXED: Backend expects PUT for updates
    return fetchWithAuth<WorkflowBackendResponse>(`/workflows/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  deleteWorkflow: async (id: number): Promise<void> => {
    return fetchWithAuth<void>(`/workflows/${id}`, {
      method: 'DELETE',
    });
  },

  publishWorkflow: async (id: number): Promise<WorkflowBackendResponse> => {
    return fetchWithAuth<WorkflowBackendResponse>(`/workflows/${id}/publish`, {
      method: 'POST',
    });
  },

  // GAP-W7 FIX: Use fetchStream for SSE consumption (backend returns StreamingResponse)
  executeWorkflow: async (
    id: number,
    inputs: Record<string, unknown> = {},
    onEvent?: (event: { type: string; data: unknown }) => void,
  ): Promise<void> => {
    return fetchStream(
      `/workflows/${id}/execute`,
      {
        method: 'POST',
        body: JSON.stringify({ inputs }),
      },
      (chunk) => {
        if (onEvent) {
          try {
            const parsed = JSON.parse(chunk);
            onEvent({ type: parsed.type || 'unknown', data: parsed });
          } catch {
            // Non-JSON chunk (e.g., [DONE] marker), ignore
          }
        }
      },
    );
  },

  cloneWorkflow: async (id: number, name?: string): Promise<WorkflowBackendResponse> => {
    // GAP-048: Clone endpoint
    // Note: Backend correctly uses get_current_user dependency for auth context
    return fetchWithAuth<WorkflowBackendResponse>(`/workflows/${id}/clone`, {
      method: 'POST',
      body: JSON.stringify({ name }),
    });
  },

  // GAP-W1/W12 FIX: Archive via dedicated POST /archive endpoint (not broken PUT with status)
  archiveWorkflow: async (id: number): Promise<WorkflowBackendResponse> => {
    return fetchWithAuth<WorkflowBackendResponse>(`/workflows/${id}/archive`, {
      method: 'POST',
    });
  },

  // GAP-W9: Workflow sharing (share, unshare, list shares)
  shareWorkflow: async (
    workflowId: number,
    userId: string,
    permission: 'view' | 'edit',
  ): Promise<{ message: string }> => {
    return fetchWithAuth<{ message: string }>(`/workflows/${workflowId}/share`, {
      method: 'POST',
      body: JSON.stringify({ user_id: userId, permission }),
    });
  },

  unshareWorkflow: async (
    workflowId: number,
    userId: string,
  ): Promise<void> => {
    return fetchWithAuth<void>(`/workflows/${workflowId}/share/${userId}`, {
      method: 'DELETE',
    });
  },

  getWorkflowShares: async (
    workflowId: number,
  ): Promise<{ shares: Array<{ user_id: string; permission: string }> }> => {
    return fetchWithAuth<{ shares: Array<{ user_id: string; permission: string }> }>(
      `/workflows/${workflowId}/shares`,
    );
  },

  // GAP-W13: Create workflow from template with provenance tracking
  createFromTemplate: async (
    templateId: number,
    versionId: number | null,
    workflowJson: unknown,
    name?: string,
    description?: string,
  ): Promise<WorkflowBackendResponse> => {
    return fetchWithAuth<WorkflowBackendResponse>('/workflows/from-template', {
      method: 'POST',
      body: JSON.stringify({
        template_id: templateId,
        template_version_id: versionId,
        workflow_json: workflowJson,
        name: name || 'Untitled Workflow',
        description,
      }),
    });
  },
};

// Workflow Scenarios API - Production workflow scenarios
export const scenariosApi = {
  /**
   * List all available workflow scenarios.
   */
  listScenarios: async (): Promise<ScenarioInfo[]> => {
    const response = await fetchWithAuth<ScenarioInfo[] | { scenarios?: ScenarioInfo[]; items?: ScenarioInfo[] }>('/workflow-scenarios');
    if (Array.isArray(response)) return response;
    if (response && typeof response === 'object') {
      const obj = response as { scenarios?: ScenarioInfo[]; items?: ScenarioInfo[] };
      if (Array.isArray(obj.scenarios)) return obj.scenarios;
      if (Array.isArray(obj.items)) return obj.items;
    }
    return [];
  },

  /**
   * Get detailed info about a specific scenario.
   */
  getScenario: async (name: string): Promise<ScenarioDetail> => {
    return fetchWithAuth<ScenarioDetail>(`/workflow-scenarios/${name}`);
  },

  /**
   * Get the workflow graph (nodes/edges) for visual editing.
   */
  getWorkflow: async (name: string): Promise<ScenarioWorkflowGraph> => {
    return fetchWithAuth<ScenarioWorkflowGraph>(`/workflow-scenarios/${name}/workflow`);
  },

  /**
   * Trigger a scenario execution with SSE streaming.
   * Returns an EventSource-compatible URL.
   */
  triggerScenario: async (
    name: string,
    inputs: Record<string, unknown>
  ): Promise<Response> => {
    const tokens = getTokens();
    const response = await fetch(`/api/workflow-scenarios/${name}/trigger`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(tokens?.access_token && { Authorization: `Bearer ${tokens.access_token}` }),
      },
      body: JSON.stringify(inputs),
    });
    return response;
  },

  /**
   * Get checkpoints for an execution.
   */
  getCheckpoints: async (executionId: string): Promise<ScenarioCheckpoint[]> => {
    return fetchWithAuth<ScenarioCheckpoint[]>(
      `/workflow-scenarios/executions/${executionId}/checkpoints`
    );
  },

  /**
   * Resume execution from a checkpoint.
   */
  resumeFromCheckpoint: async (
    name: string,
    executionId: string,
    checkpointNode: string
  ): Promise<Response> => {
    const tokens = getTokens();
    const response = await fetch(`/api/workflow-scenarios/${name}/resume`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(tokens?.access_token && { Authorization: `Bearer ${tokens.access_token}` }),
      },
      body: JSON.stringify({
        execution_id: executionId,
        checkpoint_node: checkpointNode,
      }),
    });
    return response;
  },

  /**
   * Upload a file for workflow input and return the staged file path.
   */
  uploadWorkflowFile: async (
    file: File,
    inputName: string
  ): Promise<{ path: string; filename: string }> => {
    const tokens = getTokens();
    const formData = new FormData();
    formData.append('file', file);
    formData.append('input_name', inputName);

    const baseUrl = import.meta.env.VITE_API_BASE_URL || '/api';
    const response = await fetch(`${baseUrl}/workflow-scenarios/upload-input`, {
      method: 'POST',
      headers: {
        ...(tokens?.access_token ? { Authorization: `Bearer ${tokens.access_token}` } : {}),
      },
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Upload failed' }));
      throw new Error(error.detail || 'Failed to upload file');
    }

    return response.json();
  },

  /**
   * Trigger a scenario with file inputs.
   * First uploads files, then triggers with file paths.
   */
  triggerScenarioWithFiles: async (
    name: string,
    inputs: Record<string, unknown>,
    files: Record<string, File>
  ): Promise<Response> => {
    const tokens = getTokens();

    // Upload files and collect paths
    const filePaths: Record<string, string> = {};
    for (const [inputName, file] of Object.entries(files)) {
      const result = await scenariosApi.uploadWorkflowFile(file, inputName);
      filePaths[inputName] = result.path;
    }

    // Merge file paths into inputs
    const allInputs = { ...inputs, ...filePaths };

    // Trigger with all inputs including file paths
    const response = await fetch(`/api/workflow-scenarios/${name}/trigger`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(tokens?.access_token && { Authorization: `Bearer ${tokens.access_token}` }),
      },
      body: JSON.stringify(allInputs),
    });
    return response;
  },

  // GAP-S6: Create a scenario from a template's workflow_json
  createFromTemplate: async (params: {
    name: string;
    workflow_json: unknown;
    description?: string;
    template_id?: number;
  }): Promise<{ scenario_name: string; path: string; message: string }> => {
    return fetchWithAuth<{ scenario_name: string; path: string; message: string }>(
      '/workflow-scenarios/from-template',
      {
        method: 'POST',
        body: JSON.stringify(params),
      },
    );
  },
};

// Executions API - Workflow execution history
export const executionsApi = {
  /**
   * List workflow executions with optional filtering.
   */
  list: async (params?: {
    scenario_name?: string;
    status?: string;
    limit?: number;
    offset?: number;
  }): Promise<{ executions: ExecutionSummary[]; total: number }> => {
    const searchParams = new URLSearchParams();
    if (params?.scenario_name) searchParams.set('scenario_name', params.scenario_name);
    if (params?.status) searchParams.set('status', params.status);
    if (params?.limit) searchParams.set('limit', params.limit.toString());
    if (params?.offset) searchParams.set('offset', params.offset.toString());
    const query = searchParams.toString();
    return fetchWithAuth(`/workflow-scenarios/executions${query ? `?${query}` : ''}`);
  },

  /**
   * Get full details for a specific execution.
   */
  get: async (executionId: string): Promise<ExecutionDetail> => {
    return fetchWithAuth(`/workflow-scenarios/executions/${executionId}`);
  },

  /**
   * Cancel a running execution.
   */
  cancel: async (executionId: string): Promise<ExecutionDetail> => {
    return fetchWithAuth(`/workflow-scenarios/executions/${executionId}/cancel`, {
      method: 'POST',
    });
  },

  /**
   * GAP-S3: Validate scenario inputs before triggering execution.
   * Returns validation errors if inputs are invalid, or empty array if OK.
   * Fails open: callers should catch errors and proceed with trigger.
   */
  validateInputs: async (scenarioName: string, inputs: Record<string, unknown>): Promise<{ errors: string[] }> => {
    return fetchWithAuth(`/workflow-scenarios/${scenarioName}/validate`, {
      method: 'POST',
      body: JSON.stringify({ inputs }),
    });
  },
};
