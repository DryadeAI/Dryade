// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// Settings API - Model configuration, provider registry, custom providers, commands, models

import { fetchWithAuth } from '../apiClient';
import { fetchEnterprise } from './common';
import type {
  ModelsConfig,
  ProviderInfo,
  ApiKeyInfo,
  TestConnectionResult,
  ModelCapability,
  ProviderWithCapabilities,
  ConnectionTestResult,
  ModelDiscoveryResult,
  Model,
  ProviderParamsResponse,
  InferenceParams,
} from '@/types/extended-api';
import type { CustomProviderResponse, CustomProviderCreate } from '@/types/extended-api';

// Backend uses flat fields (llm_provider, llm_model), frontend uses nested (llm: { provider, model })
// These helpers transform between the two formats

interface BackendModelConfig {
  llm_provider: string | null;
  llm_model: string | null;
  llm_endpoint: string | null;
  embedding_provider: string | null;
  embedding_model: string | null;
  embedding_endpoint: string | null;
  asr_provider: string | null;
  asr_model: string | null;
  asr_endpoint: string | null;
  tts_provider: string | null;
  tts_model: string | null;
  vision_provider: string | null;
  vision_model: string | null;
  updated_at: string | null;
  llm_inference_params: Record<string, number | string | string[]> | null;
  vision_inference_params: Record<string, number | string | string[]> | null;
  audio_inference_params: Record<string, number | string | string[]> | null;
  embedding_inference_params: Record<string, number | string | string[]> | null;
  vllm_server_params: Record<string, number | string | string[]> | null;
}

function transformBackendToFrontend(backend: BackendModelConfig): ModelsConfig {
  return {
    llm: { provider: backend.llm_provider || '', model: backend.llm_model || '' },
    embedding: { provider: backend.embedding_provider || '', model: backend.embedding_model || '' },
    audio: { provider: backend.asr_provider || '', model: backend.asr_model || '' },
    vision: { provider: backend.vision_provider || '', model: backend.vision_model || '' },
    llm_endpoint: backend.llm_endpoint || undefined,
    asr_endpoint: backend.asr_endpoint || undefined,
    embedding_endpoint: backend.embedding_endpoint || undefined,
    llm_inference_params: backend.llm_inference_params || undefined,
    vision_inference_params: backend.vision_inference_params || undefined,
    audio_inference_params: backend.audio_inference_params || undefined,
    embedding_inference_params: backend.embedding_inference_params || undefined,
    vllm_server_params: backend.vllm_server_params || undefined,
  };
}

function transformFrontendToBackend(
  capability: ModelCapability,
  config: { provider: string; model: string; endpoint?: string | null },
  inferenceParams?: InferenceParams,
  vllmServerParams?: InferenceParams
): Record<string, string | null | undefined | InferenceParams> {
  // Map frontend capability to backend field prefix
  const prefixMap: Record<ModelCapability, string> = {
    llm: 'llm',
    embedding: 'embedding',
    audio: 'asr', // Frontend "audio" maps to backend "asr"
    vision: 'vision',
  };
  const prefix = prefixMap[capability];
  const result: Record<string, string | null | undefined | InferenceParams> = {
    [`${prefix}_provider`]: config.provider,
    [`${prefix}_model`]: config.model,
  };
  // Always include endpoint when provided (even null to clear stale values)
  if (capability === 'llm' && config.endpoint !== undefined) {
    result.llm_endpoint = config.endpoint;
  }
  if (capability === 'audio' && config.endpoint !== undefined) {
    result.asr_endpoint = config.endpoint;
  }
  if (capability === 'embedding' && config.endpoint !== undefined) {
    result.embedding_endpoint = config.endpoint;
  }
  // Map capability to inference params field name
  const inferenceFieldMap: Record<ModelCapability, string> = {
    llm: 'llm_inference_params',
    embedding: 'embedding_inference_params',
    audio: 'audio_inference_params',
    vision: 'vision_inference_params',
  };
  if (inferenceParams !== undefined) {
    result[inferenceFieldMap[capability]] = inferenceParams;
  }
  if (vllmServerParams !== undefined) {
    result['vllm_server_params'] = vllmServerParams;
  }
  return result;
}

/**
 * API for model configuration management.
 * Handles provider selection, model configuration per capability, and API key management.
 */
export const modelsConfigApi = {
  /**
   * Get current model configuration.
   * GET /api/models/config
   */
  getConfig: async (): Promise<ModelsConfig> => {
    const backend = await fetchWithAuth<BackendModelConfig>('/models/config');
    return transformBackendToFrontend(backend);
  },

  /**
   * Update model configuration for a specific capability.
   * PATCH /api/models/config
   */
  updateConfig: async (
    capability: ModelCapability,
    config: { provider: string; model: string; endpoint?: string },
    inferenceParams?: InferenceParams,
    vllmServerParams?: InferenceParams
  ): Promise<ModelsConfig> => {
    const flatConfig = transformFrontendToBackend(capability, config, inferenceParams, vllmServerParams);
    const backend = await fetchWithAuth<BackendModelConfig>('/models/config', {
      method: 'PATCH',
      body: JSON.stringify(flatConfig),
    });
    return transformBackendToFrontend(backend);
  },

  /**
   * Get provider parameter support map, specs, presets.
   * GET /api/models/provider-params
   */
  getProviderParams: async (): Promise<ProviderParamsResponse> => {
    return fetchWithAuth<ProviderParamsResponse>('/models/provider-params');
  },

  /**
   * Get available providers and their models.
   * GET /api/models/providers
   */
  getProviders: async (capability?: ModelCapability): Promise<ProviderInfo[]> => {
    const query = capability ? `?capability=${capability}` : '';
    const res = await fetchWithAuth<ProviderInfo[]>(`/models/providers${query}`);
    return Array.isArray(res) ? res : [];
  },

  /**
   * Store an API key for a provider.
   * POST /api/models/keys
   */
  storeApiKey: async (provider: string, apiKey: string): Promise<{ success: boolean }> => {
    return fetchWithAuth<{ success: boolean }>('/models/keys', {
      method: 'POST',
      body: JSON.stringify({ provider, api_key: apiKey }),
    });
  },

  /**
   * Get stored API keys (masked).
   * GET /api/models/keys
   */
  getApiKeys: async (): Promise<ApiKeyInfo[]> => {
    const res = await fetchWithAuth<ApiKeyInfo[]>('/models/keys');
    return Array.isArray(res) ? res : [];
  },

  /**
   * Delete an API key for a provider.
   * DELETE /api/models/keys/{provider}
   */
  deleteApiKey: async (provider: string): Promise<void> => {
    return fetchWithAuth<void>(`/models/keys/${encodeURIComponent(provider)}`, {
      method: 'DELETE',
    });
  },

  /**
   * Test connection to a provider.
   * POST /api/models/test
   */
  testConnection: async (provider: string): Promise<TestConnectionResult> => {
    return fetchWithAuth<TestConnectionResult>('/models/test', {
      method: 'POST',
      body: JSON.stringify({ provider }),
    });
  },
};

// ============== PROVIDER REGISTRY API ==============

/**
 * API for provider registry management.
 * Handles provider discovery, capabilities, connection testing, and model discovery.
 */
export const providerRegistryApi = {
  /**
   * List all available providers with capabilities.
   * GET /api/providers
   */
  listProviders: async (): Promise<ProviderWithCapabilities[]> => {
    const providers = await fetchWithAuth<ProviderWithCapabilities[]>('/providers');
    if (!Array.isArray(providers)) return [];
    // Normalize: add 'name' alias for 'id', derive is_custom from backend
    return providers.map(p => ({
      ...p,
      name: p.id,
      is_custom: p.is_custom ?? false,
    }));
  },

  /**
   * Get single provider with full details.
   * GET /api/providers/{id}
   */
  getProvider: async (providerId: string): Promise<ProviderWithCapabilities> => {
    const provider = await fetchWithAuth<ProviderWithCapabilities>(`/providers/${encodeURIComponent(providerId)}`);
    return {
      ...provider,
      name: provider.id,
    };
  },

  /**
   * Test connection to a provider with optional custom endpoint.
   * POST /api/providers/{provider}/test
   */
  testConnection: async (
    provider: string,
    endpoint?: string
  ): Promise<ConnectionTestResult> => {
    return fetchWithAuth<ConnectionTestResult>(`/providers/${encodeURIComponent(provider)}/test`, {
      method: 'POST',
      body: JSON.stringify({ base_url: endpoint }),
    });
  },

  /**
   * Discover available models from a provider endpoint.
   * GET /api/providers/{provider}/models
   */
  discoverModels: async (
    provider: string,
    endpoint?: string
  ): Promise<ModelDiscoveryResult> => {
    const params = endpoint ? `?endpoint=${encodeURIComponent(endpoint)}` : '';
    return fetchWithAuth<ModelDiscoveryResult>(`/providers/${encodeURIComponent(provider)}/models${params}`);
  },
};

// ============== CUSTOM PROVIDERS API ==============

export const customProvidersApi = {
  list: async (): Promise<CustomProviderResponse[]> => {
    return fetchWithAuth<CustomProviderResponse[]>('/custom-providers');
  },

  create: async (data: CustomProviderCreate): Promise<CustomProviderResponse> => {
    return fetchWithAuth<CustomProviderResponse>('/custom-providers', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  update: async (slug: string, data: Partial<CustomProviderCreate>): Promise<CustomProviderResponse> => {
    return fetchWithAuth<CustomProviderResponse>(`/custom-providers/${encodeURIComponent(slug)}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  delete: async (slug: string): Promise<void> => {
    await fetchWithAuth(`/custom-providers/${encodeURIComponent(slug)}`, {
      method: 'DELETE',
    });
  },
};

// ============== COMMANDS API ==============

/**
 * Command info returned from backend
 */
export interface CommandInfo {
  name: string;
  description: string;
}

/**
 * Response from GET /api/commands
 */
interface CommandListResponse {
  commands: CommandInfo[];
}

/**
 * Request body for POST /api/commands/{name}/execute
 */
interface CommandExecuteRequest {
  args: Record<string, unknown>;
}

/**
 * Response from POST /api/commands/{name}/execute
 */
export interface CommandExecuteResponse {
  status: 'ok' | 'error';
  result?: unknown;
  error?: string;
}

/**
 * Error response when command not found (404)
 */
export interface CommandNotFoundError {
  error: string;
  suggestions: string[];
}

// Commands API - Real backend calls (36-02)
export const commandsApi = {
  /**
   * List all available commands.
   * GET /api/commands
   *
   * Returns list of registered slash commands with name and description.
   */
  list: async (): Promise<CommandListResponse> => {
    return fetchWithAuth<CommandListResponse>('/commands');
  },

  /**
   * Execute a command by name.
   * POST /api/commands/{name}/execute
   *
   * @param name - Command name (without "/" prefix)
   * @param args - Command arguments as key-value pairs
   * @returns Command execution result
   * @throws Error with suggestions if command not found
   */
  execute: async (
    name: string,
    args?: Record<string, unknown>
  ): Promise<CommandExecuteResponse> => {
    const request: CommandExecuteRequest = { args: args || {} };
    return fetchWithAuth<CommandExecuteResponse>(
      `/commands/${encodeURIComponent(name)}/execute`,
      {
        method: 'POST',
        body: JSON.stringify(request),
      }
    );
  },
};

// GAP-085: Backend uses TrainedModel, not Model
interface TrainedModelBackend {
  id: string;
  name: string;
  display_name: string;
  base_model: string; // The model it was fine-tuned from
  job_id?: string;
  status: 'available' | 'loading' | 'error' | 'deprecated';
  is_default: boolean;
  created_at: string;
  metrics?: {
    eval_score?: number;
    latency_avg_ms?: number;
    success_rate?: number;
  };
  config?: Record<string, unknown>;
}

// Trainer API has been migrated to plugins/trainer/ui
// The plugin UI bundle communicates via DryadeBridge
// See: plugins/trainer/ui/src/lib/bridge-api.ts

// Models API - Real backend calls (GAP-085, GAP-086)
// Maps to /trainer/models endpoints for trained models
export const modelsApi = {
  // GET /trainer/models - List trained models
  getModels: async (): Promise<{ models: Model[]; total: number }> => {
    const response = await fetchEnterprise<{
      items: TrainedModelBackend[];
      total: number;
    }>('/trainer/models');

    const models: Model[] = response.items.map((m) => ({
      id: m.id,
      name: m.name,
      display_name: m.display_name,
      provider: 'Dryade', // Trained models are Dryade-hosted
      status: m.status === 'available' ? 'available' :
              m.status === 'loading' ? 'loading' :
              m.status === 'deprecated' ? 'deprecated' : 'error',
      is_default: m.is_default,
      is_custom: true, // All trained models are custom
      base_model: m.base_model,
      job_id: m.job_id,
      metrics: m.metrics ? {
        latency_avg_ms: m.metrics.latency_avg_ms || 0,
        success_rate: m.metrics.success_rate || 0,
        eval_score: m.metrics.eval_score,
      } : undefined,
      created_at: m.created_at,
    }));

    return { models, total: response.total };
  },

  // GET /trainer/models/{id} - Get single model
  getModel: async (id: string): Promise<Model> => {
    const m = await fetchEnterprise<TrainedModelBackend>(`/trainer/models/${id}`);
    return {
      id: m.id,
      name: m.name,
      display_name: m.display_name,
      provider: 'Dryade',
      status: m.status === 'available' ? 'available' :
              m.status === 'loading' ? 'loading' :
              m.status === 'deprecated' ? 'deprecated' : 'error',
      is_default: m.is_default,
      is_custom: true,
      base_model: m.base_model,
      job_id: m.job_id,
      metrics: m.metrics ? {
        latency_avg_ms: m.metrics.latency_avg_ms || 0,
        success_rate: m.metrics.success_rate || 0,
        eval_score: m.metrics.eval_score,
      } : undefined,
      created_at: m.created_at,
    };
  },

  // POST /trainer/models/{id}/set-default - Set model as default
  setDefault: async (id: string): Promise<Model> => {
    const response = await fetchEnterprise<TrainedModelBackend>(
      `/trainer/models/${id}/set-default`,
      { method: 'POST' }
    );
    return modelsApi.getModel(response.id);
  },

  // DELETE /trainer/models/{id} - Delete a model
  deleteModel: async (id: string): Promise<void> => {
    return fetchEnterprise<void>(`/trainer/models/${id}`, {
      method: 'DELETE',
    });
  },

  // PATCH /trainer/models/{id} - Update model metadata
  updateModel: async (
    id: string,
    data: Partial<{
      name: string;
      display_name: string;
      status: string;
    }>
  ): Promise<Model> => {
    await fetchEnterprise<TrainedModelBackend>(`/trainer/models/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
    return modelsApi.getModel(id);
  },

  // POST /trainer/models - Create a new model (GAP-085, GAP-116)
  createModel: async (data: {
    name: string;
    display_name?: string;
    model_family: string;
    base_model: string;
    version?: string;
    job_id?: string;
  }): Promise<Model> => {
    const response = await fetchEnterprise<TrainedModelBackend>('/trainer/models', {
      method: 'POST',
      body: JSON.stringify(data),
    });
    return modelsApi.getModel(response.id);
  },

  // POST /trainer/models/compare - Compare multiple models (GAP-089)
  compareModels: async (
    modelIds: string[]
  ): Promise<{
    models: Model[];
    comparison: Record<string, Record<string, number>>;
  }> => {
    return fetchEnterprise<{
      models: Model[];
      comparison: Record<string, Record<string, number>>;
    }>('/trainer/models/compare', {
      method: 'POST',
      body: JSON.stringify({ model_ids: modelIds }),
    });
  },

  // GET /trainer/models/{id}/metrics - Get detailed model metrics (GAP-089)
  getModelMetrics: async (id: string): Promise<Record<string, number>> => {
    return fetchEnterprise<Record<string, number>>(`/trainer/models/${id}/metrics`);
  },

  // GET /trainer/routing/options - Get routing options for model selection (GAP-090)
  getRoutingOptions: async (): Promise<{
    models: Array<{ id: string; name: string; suitable_for: string[] }>;
  }> => {
    return fetchEnterprise<{
      models: Array<{ id: string; name: string; suitable_for: string[] }>;
    }>('/trainer/routing/options');
  },

  // POST /trainer/routing/classify - Classify message for model routing (GAP-090)
  classifyForRouting: async (
    message: string
  ): Promise<{
    recommended_model: string;
    confidence: number;
    alternatives: Array<{ model: string; score: number }>;
  }> => {
    return fetchEnterprise<{
      recommended_model: string;
      confidence: number;
      alternatives: Array<{ model: string; score: number }>;
    }>('/trainer/routing/classify', {
      method: 'POST',
      body: JSON.stringify({ message }),
    });
  },
};
