// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// Plugins, Marketplace, Slots, Templates & Org Templates API

import { fetchWithAuth, getTokens } from '../apiClient';
import type { Plugin, CatalogResponse, MarketplacePlugin } from '@/types/extended-api';
import type { PluginManifest } from '@/plugins/types/pluginManifest';
import type {
  Template,
  CreateTemplateRequest,
  UpdateTemplateRequest,
  TemplatesListResponse,
  CategoriesResponse,
  TemplateCategory,
} from '@/types/templates';
import type { WorkflowBackendResponse } from './workflows';

// Backend plugin types
interface PluginInfoBackend {
  name: string;
  version: string;
  description: string;
  loaded: boolean;
  enabled: boolean;
  has_ui: boolean;
  icon: string | null;
  required_tier: string | null;
}

interface PluginListBackendResponse {
  plugins: PluginInfoBackend[];
  count: number;
}

interface PluginDetailBackendResponse {
  name: string;
  version: string;
  description: string;
  loaded: boolean;
  registered: boolean;
  enabled: boolean;
  has_ui?: boolean;
  required_tier?: string | null;
  api_paths?: string[] | null;
}

interface PluginConfigBackendResponse {
  name: string;
  config: Record<string, unknown>;
  schema?: Record<string, unknown> | null;
  note?: string | null;
}

interface PluginStatsSummary {
  total: number;
  enabled: number;
  disabled: number;
  by_category: Record<string, number>;
}

const toDisplayName = (name: string): string => {
  return name
    .replace(/[_-]+/g, ' ')
    .split(' ')
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
};

const derivePluginCategory = (name: string): Plugin['category'] => {
  const pipeline = new Set(['semantic_cache', 'sandbox', 'file_safety', 'self_healing', 'safety']);
  const utility = new Set(['cost_tracker', 'checkpoint', 'debugger', 'replay', 'clarify', 'escalation']);
  if (pipeline.has(name)) return 'pipeline';
  if (utility.has(name)) return 'utility';
  return 'backend';
};

const mapPlugin = (backend: PluginInfoBackend): Plugin => {
  return {
    name: backend.name,
    display_name: toDisplayName(backend.name),
    category: derivePluginCategory(backend.name),
    status: backend.loaded ? (backend.enabled ? 'enabled' : 'disabled') : 'missing',
    version: backend.version,
    has_config: true,
    has_ui: backend.has_ui ?? false,
    required_tier: backend.required_tier,
    description: backend.description,
    icon: backend.icon ?? undefined,
  };
};

// Plugins API - Real backend calls
export const pluginsApi = {
  // GET /plugins
  getPlugins: async (): Promise<{ plugins: Plugin[]; total: number }> => {
    const response = await fetchWithAuth<PluginListBackendResponse>('/plugins');
    return {
      plugins: response.plugins.map(mapPlugin),
      total: response.count,
    };
  },

  // GET /plugins/{name}
  getPlugin: async (name: string): Promise<Plugin> => {
    const response = await fetchWithAuth<PluginDetailBackendResponse>(`/plugins/${name}`);
    return mapPlugin({ ...response, has_ui: response.has_ui ?? false, required_tier: response.required_tier ?? null });
  },

  // POST /plugins/{name}/toggle
  togglePlugin: async (name: string, enabled: boolean): Promise<Plugin> => {
    const response = await fetchWithAuth<PluginDetailBackendResponse>(`/plugins/${name}/toggle`, {
      method: 'POST',
      body: JSON.stringify({ enabled }),
    });
    return mapPlugin({ ...response, has_ui: response.has_ui ?? false, required_tier: response.required_tier ?? null });
  },

  // GET /plugins/{name}/config
  getPluginConfig: async (name: string): Promise<Record<string, unknown>> => {
    const response = await fetchWithAuth<PluginConfigBackendResponse>(`/plugins/${name}/config`);
    return response.config || {};
  },

  // GET /plugins/{name}/config — returns config + schema together
  getPluginConfigWithSchema: async (name: string): Promise<{ config: Record<string, unknown>; schema: Record<string, unknown> | null }> => {
    const response = await fetchWithAuth<PluginConfigBackendResponse>(`/plugins/${name}/config`);
    return {
      config: response.config || {},
      schema: response.schema ?? null,
    };
  },

  // PATCH /plugins/{name}/config
  updatePluginConfig: async (name: string, patch: Record<string, unknown>): Promise<void> => {
    await fetchWithAuth<PluginConfigBackendResponse>(`/plugins/${name}/config`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    });
  },

  // POST /plugins/install
  installPlugin: async (path: string): Promise<Record<string, unknown>> => {
    return fetchWithAuth<Record<string, unknown>>('/plugins/install', {
      method: 'POST',
      body: JSON.stringify({ path }),
    });
  },

  // DELETE /plugins/{name}
  uninstallPlugin: async (name: string): Promise<void> => {
    await fetchWithAuth<void>(`/plugins/${name}`, {
      method: 'DELETE',
    });
  },

  getStatsSummary: async (): Promise<PluginStatsSummary> => {
    const { plugins } = await pluginsApi.getPlugins();
    const by_category: Record<string, number> = {};
    for (const plugin of plugins) {
      by_category[plugin.category] = (by_category[plugin.category] || 0) + 1;
    }
    const enabled = plugins.filter((p) => p.status === 'enabled').length;
    const disabled = plugins.filter((p) => p.status === 'disabled').length;
    return {
      total: plugins.length,
      enabled,
      disabled,
      by_category,
    };
  },

  // GET /plugins/{name}/ui/manifest
  getPluginUIManifest: async (name: string): Promise<PluginManifest | null> => {
    try {
      const response = await fetchWithAuth<PluginManifest>(`/plugins/${name}/ui/manifest`);
      return response;
    } catch (error) {
      // 404 means plugin has no UI - not an error
      if (error instanceof Error && error.message.includes('404')) {
        return null;
      }
      throw error;
    }
  },

  // GET /plugins/{name}/ui/bundle - returns raw text
  getPluginUIBundle: async (name: string): Promise<string> => {
    const tokens = getTokens();
    const baseUrl = import.meta.env.VITE_API_BASE_URL || '/api';
    const response = await fetch(`${baseUrl}/plugins/${name}/ui/bundle`, {
      headers: {
        ...(tokens?.access_token ? { Authorization: `Bearer ${tokens.access_token}` } : {}),
      },
    });
    if (!response.ok) {
      throw new Error(`Failed to fetch plugin bundle: ${response.status}`);
    }
    return response.text();
  },

  // GET /plugins/{name}/ui/styles - returns raw CSS text (optional)
  getPluginUIStyles: async (name: string): Promise<string | null> => {
    const tokens = getTokens();
    const baseUrl = import.meta.env.VITE_API_BASE_URL || '/api';
    try {
      const response = await fetch(`${baseUrl}/plugins/${name}/ui/styles`, {
        headers: {
          ...(tokens?.access_token ? { Authorization: `Bearer ${tokens.access_token}` } : {}),
        },
      });
      if (!response.ok) {
        if (response.status === 404) {
          // Styles are optional - plugin may not have them
          return null;
        }
        throw new Error(`Failed to fetch plugin styles: ${response.status}`);
      }
      return response.text();
    } catch (error) {
      // Network error or other - styles are optional, don't fail load
      console.debug(`Plugin ${name} styles not available:`, error);
      return null;
    }
  },

  // List all plugins with UI capability
  // Uses has_ui from plugin list to avoid N+1 API calls
  listUIPlugins: async (): Promise<Array<{ name: string; manifest: PluginManifest }>> => {
    const { plugins } = await pluginsApi.getPlugins();
    const uiPlugins: Array<{ name: string; manifest: PluginManifest }> = [];

    // Filter to only plugins with has_ui=true before fetching manifests
    const pluginsWithUI = plugins.filter(p => p.has_ui);

    for (const plugin of pluginsWithUI) {
      const manifest = await pluginsApi.getPluginUIManifest(plugin.name);
      if (manifest?.has_ui) {
        uiPlugins.push({ name: plugin.name, manifest });
      }
    }

    return uiPlugins;
  },

  /**
   * Trigger PM to check marketplace for allowlist updates immediately.
   * POST /plugins/check-updates
   * Core proxies this to PM's internal trigger endpoint on port 9472.
   */
  checkForUpdates: async (): Promise<{ status: string; message?: string }> => {
    return fetchWithAuth<{ status: string; message?: string }>('/plugins/check-updates', {
      method: 'POST',
    });
  },

  /**
   * Get the status of the last allowlist update received from PM.
   * GET /plugins/update-status
   */
  getUpdateStatus: async (): Promise<{
    last_updated: string | null;
    version: number | null;
    has_update: boolean;
  }> => {
    return fetchWithAuth<{
      last_updated: string | null;
      version: number | null;
      has_update: boolean;
    }>('/plugins/update-status');
  },

  /**
   * Upload a .dryadepkg file for installation.
   * PM will verify signatures, check tier, decrypt, and install.
   */
  uploadPackage: async (
    file: File,
    onProgress?: (progress: number) => void
  ): Promise<{ success: boolean; plugin_name: string; message: string }> => {
    const tokens = getTokens();
    const baseUrl = import.meta.env.VITE_API_BASE_URL || '/api';

    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', `${baseUrl}/plugins/upload`);

      if (tokens?.access_token) {
        xhr.setRequestHeader('Authorization', `Bearer ${tokens.access_token}`);
      }

      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable && onProgress) {
          const percent = Math.round((event.loaded * 100) / event.total);
          onProgress(percent);
        }
      };

      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const response = JSON.parse(xhr.responseText);
            resolve(response);
          } catch {
            reject(new Error('Invalid response from server'));
          }
        } else {
          try {
            const errorResponse = JSON.parse(xhr.responseText);
            const error = new Error(errorResponse.detail || 'Upload failed') as Error & { response?: { data: { detail: string } } };
            error.response = { data: { detail: errorResponse.detail || 'Upload failed' } };
            reject(error);
          } catch {
            reject(new Error(`Upload failed: ${xhr.status}`));
          }
        }
      };

      xhr.onerror = () => {
        reject(new Error('Network error during upload'));
      };

      const formData = new FormData();
      formData.append('file', file);
      xhr.send(formData);
    });
  },
};

// ============== MARKETPLACE API ==============

export const marketplaceApi = {
  /**
   * Fetch the plugin catalog with optional filters.
   * GET /api/marketplace/catalog
   */
  getCatalog: async (params?: {
    category?: string;
    search?: string;
    tier?: string;
  }): Promise<CatalogResponse> => {
    const searchParams = new URLSearchParams();
    if (params?.category) searchParams.set('category', params.category);
    if (params?.search) searchParams.set('search', params.search);
    if (params?.tier) searchParams.set('tier', params.tier);
    const query = searchParams.toString();
    return fetchWithAuth<CatalogResponse>(
      `/marketplace/catalog${query ? `?${query}` : ''}`
    );
  },

  /**
   * Install (activate) a locally-present plugin.
   * POST /api/marketplace/install
   */
  installPlugin: async (
    pluginName: string
  ): Promise<{ success: boolean; message: string; plugin_name: string }> => {
    return fetchWithAuth<{ success: boolean; message: string; plugin_name: string }>(
      '/marketplace/install',
      {
        method: 'POST',
        body: JSON.stringify({ plugin_name: pluginName }),
      }
    );
  },

  /**
   * Get available plugin categories.
   * GET /api/marketplace/categories
   */
  getCategories: async (): Promise<{ categories: string[] }> => {
    return fetchWithAuth<{ categories: string[] }>('/marketplace/categories');
  },
};

// Slot registration types (matches backend SlotRegistration)
export interface SlotRegistrationResponse {
  plugin_name: string;
  component_name: string;
  priority: number;
  props: Record<string, unknown>;
}

// Slots API - Plugin UI slot system (Phase 70.0.1)
export const slotsApi = {
  /**
   * Get all slot registrations from all plugins
   */
  async getAll(): Promise<Record<string, SlotRegistrationResponse[]>> {
    return fetchWithAuth<Record<string, SlotRegistrationResponse[]>>('/plugins/slots');
  },

  /**
   * Get registrations for a specific slot
   */
  async getSlot(slotName: string): Promise<SlotRegistrationResponse[]> {
    return fetchWithAuth<SlotRegistrationResponse[]>(`/plugins/slots/${slotName}`);
  },

  /**
   * Get registrations for a specific plugin
   */
  async getPluginSlots(pluginName: string): Promise<Record<string, SlotRegistrationResponse[]>> {
    return fetchWithAuth<Record<string, SlotRegistrationResponse[]>>(`/plugins/${pluginName}/slots`);
  },
};

// ============================================================================
// Templates API - Plugin-provided workflow templates (Phase 70.1)
// ============================================================================

export const templatesApi = {
  /**
   * Get available template categories.
   */
  getCategories: async (): Promise<CategoriesResponse> => {
    return fetchWithAuth<CategoriesResponse>('/templates/categories');
  },

  /**
   * List user's templates, optionally filtered by category.
   */
  getTemplates: async (category?: TemplateCategory): Promise<TemplatesListResponse> => {
    const params = new URLSearchParams();
    if (category) params.set('category', category);
    const query = params.toString();
    return fetchWithAuth<TemplatesListResponse>(`/templates${query ? `?${query}` : ''}`);
  },

  /**
   * Get a single template by ID.
   */
  getTemplate: async (id: number): Promise<Template> => {
    return fetchWithAuth<Template>(`/templates/${id}`);
  },

  /**
   * Create a new template from current workflow.
   */
  createTemplate: async (data: CreateTemplateRequest): Promise<Template> => {
    return fetchWithAuth<Template>('/templates', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  /**
   * Update an existing template.
   */
  updateTemplate: async (id: number, data: UpdateTemplateRequest): Promise<Template> => {
    return fetchWithAuth<Template>(`/templates/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  /**
   * Delete a template.
   */
  deleteTemplate: async (id: number): Promise<void> => {
    return fetchWithAuth<void>(`/templates/${id}`, {
      method: 'DELETE',
    });
  },
};

// ============================================================================
// Org Templates API - Main-app integration for organization templates (GAP-T1)
// These methods provide access to org template data outside the plugin iframe,
// enabling cross-feature integration (e.g., template-originated workflow creation).
// ============================================================================

/** Org template summary for listing. */
export interface OrgTemplate {
  id: number;
  name: string;
  description: string;
  category: string;
  organization_id: string;
  created_by: string;
  visibility: string;
  status: string;
  created_at: string;
  updated_at: string;
}

/** Template version summary. */
export interface TemplateVersion {
  id: number;
  template_id: number;
  version_number: string;
  workflow_json: unknown;
  changelog: string;
  created_at: string;
}

export const orgTemplatesApi = {
  /**
   * List org templates for a given organization.
   */
  list: async (
    orgId: string,
    params?: { category?: string; status?: string },
  ): Promise<{ items: OrgTemplate[]; total: number }> => {
    const searchParams = new URLSearchParams();
    if (params?.category) searchParams.set('category', params.category);
    if (params?.status) searchParams.set('status', params.status);
    const query = searchParams.toString();
    return fetchWithAuth<{ items: OrgTemplate[]; total: number }>(
      `/templates/org/${orgId}${query ? `?${query}` : ''}`,
    );
  },

  /**
   * Get a single org template by ID.
   */
  get: async (templateId: number): Promise<OrgTemplate> => {
    return fetchWithAuth<OrgTemplate>(`/templates/org/${templateId}`);
  },

  /**
   * Get all versions for an org template.
   */
  getVersions: async (templateId: number): Promise<TemplateVersion[]> => {
    return fetchWithAuth<TemplateVersion[]>(`/templates/org/${templateId}/versions`);
  },

  /**
   * Create a workflow from an org template version.
   * Delegates to workflowsApi.createFromTemplate for the actual POST call.
   */
  createWorkflowFromTemplate: async (
    templateId: number,
    versionId: number,
    workflowJson: unknown,
    name?: string,
  ): Promise<WorkflowBackendResponse> => {
    return fetchWithAuth<WorkflowBackendResponse>('/workflows/from-template', {
      method: 'POST',
      body: JSON.stringify({
        template_id: templateId,
        template_version_id: versionId,
        workflow_json: workflowJson,
        name,
      }),
    });
  },
};
