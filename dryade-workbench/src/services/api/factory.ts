// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// Factory API - Agent Factory lifecycle management
// CRUD + rollback for factory-created artifacts (agents, tools, skills)

import { fetchWithAuth } from '../apiClient';

// ---------------------------------------------------------------------------
// Types (matching core/factory/models.py + core/api/routes/factory.py)
// ---------------------------------------------------------------------------

export type ArtifactType = 'agent' | 'tool' | 'skill';

export type ArtifactStatus =
  | 'configuring'
  | 'pending_approval'
  | 'scaffolded'
  | 'testing'
  | 'active'
  | 'failed'
  | 'archived'
  | 'rolled_back';

export interface FactoryArtifact {
  id: string;
  name: string;
  artifact_type: ArtifactType;
  framework: string;
  version: number;
  status: ArtifactStatus;
  source_prompt: string;
  config_json: Record<string, unknown>;
  artifact_path: string;
  test_result: string | null;
  test_passed: boolean;
  test_iterations: number;
  created_at: string;
  updated_at: string;
  created_by: string;
  trigger: string;
  tags: string[];
}

export interface CreateArtifactRequest {
  goal: string;
  suggested_name?: string;
  artifact_type?: string;
  framework?: string;
  test_task?: string;
  max_test_iterations?: number;
  fast_path?: boolean;
}

export interface CreationResult {
  success: boolean;
  artifact_name: string;
  artifact_type: string;
  framework: string;
  artifact_path: string;
  artifact_id: string;
  version: number;
  test_passed: boolean;
  test_iterations: number;
  test_output: string | null;
  message: string;
  config_json: Record<string, unknown>;
  created_at: string;
  duration_seconds: number;
  deduplication_warnings: string[];
}

export interface ArtifactListResponse {
  items: FactoryArtifact[];
  count: number;
}

// ---------------------------------------------------------------------------
// API client (mirrors agents.ts pattern with fetchWithAuth)
// ---------------------------------------------------------------------------

export const factoryApi = {
  /** List all factory artifacts with optional type/status filters. */
  list: async (params?: {
    type?: string;
    status?: string;
  }): Promise<ArtifactListResponse> => {
    const searchParams = new URLSearchParams();
    if (params?.type) searchParams.set('type', params.type);
    if (params?.status) searchParams.set('status', params.status);
    const query = searchParams.toString();

    return fetchWithAuth<ArtifactListResponse>(
      `/factory${query ? `?${query}` : ''}`
    );
  },

  /** Get a single factory artifact by name. */
  get: async (name: string): Promise<FactoryArtifact> => {
    return fetchWithAuth<FactoryArtifact>(`/factory/${encodeURIComponent(name)}`);
  },

  /** Create a new factory artifact from a natural language goal. */
  create: async (data: CreateArtifactRequest): Promise<CreationResult> => {
    return fetchWithAuth<CreationResult>('/factory', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  /** Update an existing artifact (creates a new version via TCST pipeline). */
  update: async (
    name: string,
    data: CreateArtifactRequest
  ): Promise<CreationResult> => {
    return fetchWithAuth<CreationResult>(
      `/factory/${encodeURIComponent(name)}`,
      {
        method: 'PUT',
        body: JSON.stringify(data),
      }
    );
  },

  /** Delete (archive) a factory artifact. */
  delete: async (name: string): Promise<void> => {
    return fetchWithAuth<void>(`/factory/${encodeURIComponent(name)}`, {
      method: 'DELETE',
    });
  },

  /** Save factory settings (localStorage only — no backend endpoint). */
  saveSettings: async (
    _settings: Record<string, unknown>
  ): Promise<void> => {
    // No backend endpoint — settings stored in localStorage by FactorySection
  },

  /** Load factory settings (localStorage only — no backend endpoint). */
  getSettings: async (): Promise<Record<string, unknown> | null> => {
    // No backend endpoint — settings stored in localStorage by FactorySection
    return null;
  },

  /** Approve a pending_approval artifact and resume creation. */
  approve: async (name: string): Promise<CreationResult> => {
    return fetchWithAuth<CreationResult>(
      `/factory/${encodeURIComponent(name)}/approve`,
      { method: 'POST' }
    );
  },

  /** Rollback an artifact to a previous version. */
  rollback: async (
    name: string,
    version: number
  ): Promise<CreationResult> => {
    return fetchWithAuth<CreationResult>(
      `/factory/${encodeURIComponent(name)}/rollback`,
      {
        method: 'POST',
        body: JSON.stringify({ version }),
      }
    );
  },

};
