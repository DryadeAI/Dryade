// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// Knowledge API - Knowledge base management and search

import { fetchWithAuth, getTokens } from '../apiClient';
import type { KnowledgeSource, SearchResult } from '@/types/extended-api';

// Backend knowledge types
interface KnowledgeSourceBackend {
  id: string;
  name: string;
  source_type: string; // 'PDFKnowledgeSource', 'TextFileKnowledgeSource', etc.
  file_paths: string[];
  description?: string;
  crew_ids: string[];
  agent_ids: string[];
  chunk_count?: number;    // Backend exposes this
  created_at?: string;     // Backend exposes this after Plan 01
}

interface UploadResponseBackend {
  id: string;
  name: string;
  source_type: string; // 'pdf' or 'text'
  file_path: string;
}

interface QueryResultBackend {
  content: string;
  score: number;
  metadata: Record<string, unknown>;
  source_id?: string;
}

interface QueryResponseBackend {
  results: QueryResultBackend[];
  sources_used: string[];
  query: string;
  total_results: number;
}

// Helper to map backend source_type to frontend type
const mapSourceType = (backendType: string): 'pdf' | 'text' | 'md' | 'docx' => {
  if (backendType.toLowerCase().includes('pdf')) return 'pdf';
  if (backendType.toLowerCase().includes('markdown') || backendType.toLowerCase() === 'md') return 'md';
  if (backendType.toLowerCase().includes('text')) return 'text';
  if (backendType.toLowerCase().includes('csv')) return 'text';
  return 'text';
};

// Knowledge API - Real backend calls (GAP-069 through GAP-071)
export const knowledgeApi = {
  // GET /api/knowledge - List all knowledge sources
  getSources: async (): Promise<{ sources: KnowledgeSource[]; total: number }> => {
    const response = await fetchWithAuth<{ sources: KnowledgeSourceBackend[] }>('/knowledge');

    const sources: KnowledgeSource[] = response.sources.map((s) => ({
      id: s.id,
      name: s.name,
      source_type: mapSourceType(s.source_type),
      chunk_count: s.chunk_count ?? 0,
      created_at: s.created_at || new Date().toISOString(),
      crews: s.crew_ids || [],
      agents: s.agent_ids || [],
      size_bytes: undefined, // Not available from backend
      status: 'ready' as const, // Backend doesn't track status
      description: s.description,
      file_paths: s.file_paths,
    }));

    return { sources, total: sources.length };
  },

  // GET /api/knowledge/{source_id} - Get single source
  getSource: async (id: string): Promise<KnowledgeSource> => {
    const response = await fetchWithAuth<KnowledgeSourceBackend>(`/knowledge/${id}`);

    return {
      id: response.id,
      name: response.name,
      source_type: mapSourceType(response.source_type),
      chunk_count: response.chunk_count ?? 0,
      created_at: response.created_at || new Date().toISOString(),
      crews: response.crew_ids || [],
      agents: response.agent_ids || [],
      size_bytes: undefined,
      status: 'ready' as const,
      description: response.description,
      file_paths: response.file_paths,
    };
  },

  // GAP-069: POST /api/knowledge/upload with multipart form
  uploadSource: async (
    file: File,
    metadata?: { crews?: string[]; agents?: string[]; name?: string; description?: string }
  ): Promise<KnowledgeSource> => {
    const formData = new FormData();
    formData.append('file', file);
    if (metadata?.name) {
      formData.append('name', metadata.name);
    }
    if (metadata?.description) {
      formData.append('description', metadata.description);
    }
    if (metadata?.crews && metadata.crews.length > 0) {
      formData.append('crew_ids', metadata.crews.join(','));
    }
    if (metadata?.agents && metadata.agents.length > 0) {
      formData.append('agent_ids', metadata.agents.join(','));
    }

    // Use fetch directly for multipart - fetchWithAuth sets Content-Type to JSON
    const tokens = getTokens();
    const baseUrl = import.meta.env.VITE_API_BASE_URL || '/api';
    const response = await fetch(`${baseUrl}/knowledge/upload`, {
      method: 'POST',
      headers: {
        ...(tokens?.access_token ? { Authorization: `Bearer ${tokens.access_token}` } : {}),
      },
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Upload failed' }));
      throw new Error(error.detail || 'Upload failed');
    }

    const data = (await response.json()) as UploadResponseBackend;
    return {
      id: data.id,
      name: data.name,
      source_type: mapSourceType(data.source_type),
      chunk_count: 0, // Just uploaded, chunking in progress
      created_at: new Date().toISOString(),
      crews: metadata?.crews || [],
      agents: metadata?.agents || [],
      size_bytes: file.size,
      status: 'processing' as const, // Newly uploaded starts as processing
      file_paths: [data.file_path],
    };
  },

  // GAP-070: POST /api/knowledge/query with threshold and pagination
  search: async (
    query: string,
    options?: {
      source_ids?: string[];
      threshold?: number;
      limit?: number;
      offset?: number;
    }
  ): Promise<{ results: SearchResult[]; totalResults: number }> => {
    const response = await fetchWithAuth<QueryResponseBackend>('/knowledge/query', {
      method: 'POST',
      body: JSON.stringify({
        query,
        source_ids: options?.source_ids,
        score_threshold: options?.threshold ?? 0.3, // Backend uses score_threshold (RRF-calibrated default)
        limit: options?.limit || 10,
        offset: options?.offset || 0,
      }),
    });

    return {
      results: response.results.map((r) => ({
        content: r.content,
        score: r.score,
        metadata: {
          source_id: r.source_id || (r.metadata?.source_id as string),
          source_name: r.metadata?.source_name as string | undefined,
          page: r.metadata?.page as number | undefined,
          chunk_index: r.metadata?.chunk_index as number | undefined,
        },
      })),
      totalResults: response.total_results,
    };
  },

  // DELETE /api/knowledge/{source_id}
  deleteSource: async (id: string): Promise<void> => {
    return fetchWithAuth<void>(`/knowledge/${id}`, {
      method: 'DELETE',
    });
  },

  // POST /knowledge/{source_id}/bind
  bindToAgent: async (sourceId: string, agentName: string): Promise<void> => {
    const current = await knowledgeApi.getSource(sourceId);
    const existingAgents = current.agents ?? [];
    const agentIds = Array.from(new Set([...existingAgents, agentName]));
    await fetchWithAuth<void>(`/knowledge/${sourceId}/bind`, {
      method: 'POST',
      body: JSON.stringify({ agent_ids: agentIds }),
    });
  },

  // Partial unbind via POST /bind with updated agent_ids
  unbindFromAgent: async (sourceId: string, agentName: string): Promise<void> => {
    const current = await knowledgeApi.getSource(sourceId);
    const existingAgents = current.agents ?? [];
    const agentIds = existingAgents.filter((id) => id !== agentName);
    await fetchWithAuth<void>(`/knowledge/${sourceId}/bind`, {
      method: 'POST',
      body: JSON.stringify({ agent_ids: agentIds }),
    });
  },

  // GET /knowledge/{source_id}/chunks
  getChunks: async (
    sourceId: string,
    params?: { limit?: number; offset?: number }
  ): Promise<{ chunks: Array<{ id: string; content: string; index: number }> }> => {
    const response = await fetchWithAuth<{ chunks: string[]; total: number }>(
      `/knowledge/${sourceId}/chunks`
    );

    const offset = params?.offset ?? 0;
    const limit = params?.limit ?? response.chunks.length;
    const page = response.chunks.slice(offset, offset + limit);
    return {
      chunks: page.map((content, index) => ({
        id: `${sourceId}-${offset + index}`,
        content,
        index: offset + index,
      })),
    };
  },
};

// Advanced Knowledge Plugin API (Team tier)
interface AdvancedQueryResultBackend {
  content: string;
  score: number;
  rerank_score: number | null;
  metadata: Record<string, unknown>;
  source_id: string | null;
}

interface AdvancedQueryResponseBackend {
  results: AdvancedQueryResultBackend[];
  query: string;
  query_variants: string[];
  strategies_used: string[];
  total_results: number;
}

export const advancedKnowledgeApi = {
  // Check if advanced plugin is available (Team tier)
  isAvailable: async (): Promise<boolean> => {
    try {
      // Try a minimal query to check if the endpoint responds
      await fetchWithAuth<unknown>('/knowledge/advanced/query', {
        method: 'POST',
        body: JSON.stringify({ query: 'health_check', limit: 1 }),
      });
      return true;
    } catch {
      return false;
    }
  },

  // POST /api/knowledge/advanced/query
  query: async (
    query: string,
    options?: {
      limit?: number;
      source_ids?: string[];
      multi_query?: boolean;
      hyde?: boolean;
      rerank?: boolean;
    }
  ): Promise<{
    results: SearchResult[];
    query_variants: string[];
    strategies_used: string[];
  }> => {
    const response = await fetchWithAuth<AdvancedQueryResponseBackend>(
      '/knowledge/advanced/query',
      {
        method: 'POST',
        body: JSON.stringify({
          query,
          limit: options?.limit || 10,
          source_ids: options?.source_ids,
          multi_query: options?.multi_query ?? true,
          hyde: options?.hyde ?? true,
          rerank: options?.rerank ?? true,
        }),
      }
    );

    return {
      results: response.results.map((r) => ({
        content: r.content,
        score: r.rerank_score ?? r.score,
        metadata: {
          source_id: r.source_id || (r.metadata?.source_id as string),
          source_name: (r.metadata?.source_name || r.metadata?.name) as string | undefined,
          page: r.metadata?.page as number | undefined,
          chunk_index: r.metadata?.chunk_index as number | undefined,
        },
      })),
      query_variants: response.query_variants,
      strategies_used: response.strategies_used,
    };
  },
};
