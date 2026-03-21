// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// Loop Engine API — CRUD, lifecycle, and execution history

import { fetchWithAuth } from '../apiClient';

// ============================================================================
// Types
// ============================================================================

export interface Loop {
  id: string;
  name: string;
  target_type: 'workflow' | 'agent' | 'skill' | 'orchestrator_task';
  target_id: string;
  trigger_type: 'cron' | 'interval' | 'oneshot';
  schedule: string;
  timezone: string;
  enabled: boolean;
  config: Record<string, unknown> | null;
  created_by: string | null;
  created_at: string | null;
  updated_at: string | null;
  last_run_at: string | null;
  next_run_at: string | null;
}

export interface LoopExecution {
  id: string;
  loop_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  result: Record<string, unknown> | null;
  error: string | null;
  attempt: number;
  trigger_source: string;
  created_at: string | null;
}

export interface LoopCreate {
  name: string;
  target_type: string;
  target_id: string;
  trigger_type: string;
  schedule: string;
  timezone?: string;
  config?: Record<string, unknown> | null;
  enabled?: boolean;
}

export interface LoopUpdate {
  name?: string;
  schedule?: string;
  config?: Record<string, unknown> | null;
  enabled?: boolean;
  timezone?: string;
}

interface LoopListResponse {
  items: Loop[];
  total: number;
}

interface ExecutionListResponse {
  items: LoopExecution[];
  total: number;
}

// ============================================================================
// API Client
// ============================================================================

export const loopsApi = {
  create: (data: LoopCreate): Promise<Loop> =>
    fetchWithAuth<Loop>('/loops', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  list: (params?: {
    target_type?: string;
    enabled?: boolean;
  }): Promise<LoopListResponse> => {
    const searchParams = new URLSearchParams();
    if (params?.target_type) searchParams.set('target_type', params.target_type);
    if (params?.enabled !== undefined) searchParams.set('enabled', String(params.enabled));
    const qs = searchParams.toString();
    return fetchWithAuth<LoopListResponse>(`/loops${qs ? `?${qs}` : ''}`);
  },

  get: (id: string): Promise<Loop> =>
    fetchWithAuth<Loop>(`/loops/${id}`),

  update: (id: string, data: LoopUpdate): Promise<Loop> =>
    fetchWithAuth<Loop>(`/loops/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  delete: (id: string): Promise<void> =>
    fetchWithAuth<void>(`/loops/${id}`, { method: 'DELETE' }),

  trigger: (id: string): Promise<LoopExecution> =>
    fetchWithAuth<LoopExecution>(`/loops/${id}/trigger`, { method: 'POST' }),

  pause: (id: string): Promise<Loop> =>
    fetchWithAuth<Loop>(`/loops/${id}/pause`, { method: 'POST' }),

  resume: (id: string): Promise<Loop> =>
    fetchWithAuth<Loop>(`/loops/${id}/resume`, { method: 'POST' }),

  getExecutions: (
    loopId: string,
    params?: { status?: string; limit?: number; offset?: number }
  ): Promise<ExecutionListResponse> => {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set('status', params.status);
    if (params?.limit) searchParams.set('limit', String(params.limit));
    if (params?.offset) searchParams.set('offset', String(params.offset));
    const qs = searchParams.toString();
    return fetchWithAuth<ExecutionListResponse>(
      `/loops/${loopId}/executions${qs ? `?${qs}` : ''}`
    );
  },

  getExecution: (executionId: string): Promise<LoopExecution> =>
    fetchWithAuth<LoopExecution>(`/loops/executions/${executionId}`),
};
