// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// Monitoring API - Health, metrics, queue, cache, sandbox, healing, safety, extensions

import { fetchWithAuth } from '../apiClient';
import type {
  HealthStatus,
  DetailedHealth,
  QueueStatus,
} from '@/types/api';
import type {
  CacheStats,
  SandboxConfig,
  SandboxStats,
  CircuitBreaker,
  SafetyViolation,
  SafetyStats,
  LatencyStats,
  ModeStats,
  RecentRequest,
  CodeExecuteRequest,
  CodeExecuteResponse,
} from '@/types/extended-api';

// Re-export types from canonical location for backward compatibility
export type { LatencyStats, ModeStats, RecentRequest };

// Backend health response types (GAP-063: dict not array)
interface HealthBackendResponse {
  status: 'healthy' | 'degraded' | 'unhealthy';
  components: Record<string, {
    status: 'healthy' | 'degraded' | 'unhealthy';
    category: 'critical' | 'important' | 'optional';
    latency_ms?: number;
    message?: string;
  }>;
  timestamp: string;
}

interface DetailedHealthBackendResponse extends HealthBackendResponse {
  version: string;
  uptime_seconds: number;
  environment: string;
}

// Health API - Real backend calls with response transformation
export const healthApi = {
  getHealth: async (): Promise<HealthStatus> => {
    const response = await fetchWithAuth<HealthBackendResponse>('/health', {
      requiresAuth: false, // Health check doesn't need auth
    });

    // Transform dict to array (GAP-063) - safely handle undefined/null components
    const components = response?.components && typeof response.components === 'object'
      ? Object.entries(response.components).map(([name, component]) => ({
          name,
          ...component,
        }))
      : [];

    return {
      status: response?.status ?? 'unhealthy',
      components,
      timestamp: response?.timestamp ?? new Date().toISOString(),
    };
  },

  getDetailedHealth: async (): Promise<DetailedHealth> => {
    const response = await fetchWithAuth<DetailedHealthBackendResponse>('/health/detailed', {
      requiresAuth: false,
    });

    const components = response?.components && typeof response.components === 'object'
      ? Object.entries(response.components).map(([name, component]) => ({
          name,
          ...component,
        }))
      : [];

    return {
      status: response?.status ?? 'unhealthy',
      components,
      timestamp: response?.timestamp ?? new Date().toISOString(),
      version: response?.version ?? '0.0.0',
      uptime_seconds: response?.uptime_seconds ?? 0,
      environment: response?.environment ?? 'unknown',
    };
  },

  getReady: async (): Promise<{
    ready: boolean;
    message: string;
    timestamp?: string;
    checks?: unknown;
  }> => {
    return fetchWithAuth<{
      ready: boolean;
      message: string;
      timestamp?: string;
      checks?: unknown;
    }>('/ready', {
      requiresAuth: false,
    });
  },

  getLive: async (): Promise<{ alive: boolean; timestamp: string }> => {
    return fetchWithAuth<{ alive: boolean; timestamp: string }>('/live', {
      requiresAuth: false,
    });
  },

  // GAP-064: GET /health/metrics
  getMetrics: async (): Promise<Record<string, number>> => {
    return fetchWithAuth<Record<string, number>>('/health/metrics', {
      requiresAuth: false,
    });
  },
};

// Queue API
export const queueApi = {
  getStatus: async (): Promise<QueueStatus> => {
    return fetchWithAuth<QueueStatus>('/metrics/queue');
  },
};

export const metricsApi = {
  getLatency: async (): Promise<LatencyStats> => {
    const response = await fetchWithAuth<LatencyStats>('/metrics/latency');
    // Ensure we return valid stats even if backend returns unexpected shape
    return {
      avg_ms: response?.avg_ms ?? 0,
      p50_ms: response?.p50_ms ?? 0,
      p95_ms: response?.p95_ms ?? 0,
      p99_ms: response?.p99_ms ?? 0,
      ttft_avg_ms: response?.ttft_avg_ms ?? 0,
      total_requests: response?.total_requests ?? 0,
    };
  },

  getLatencyRecent: async (limit?: number): Promise<RecentRequest[]> => {
    const params = limit ? `?limit=${limit}` : '';
    const response = await fetchWithAuth<RecentRequest[]>(`/metrics/latency/recent${params}`);
    return Array.isArray(response) ? response : [];
  },

  getLatencyByMode: async (): Promise<ModeStats[]> => {
    const response = await fetchWithAuth<ModeStats[] | { modes?: ModeStats[]; items?: ModeStats[] }>('/metrics/latency/by-mode');
    if (Array.isArray(response)) return response;
    if (response && typeof response === 'object') {
      const obj = response as { modes?: ModeStats[]; items?: ModeStats[] };
      if (Array.isArray(obj.modes)) return obj.modes;
      if (Array.isArray(obj.items)) return obj.items;
    }
    return [];
  },
};

// Cache API - Real backend calls (GAP-072 through GAP-075)
export const cacheApi = {
  // GAP-072: GET /cache/stats
  getStats: async (): Promise<CacheStats> => {
    return fetchWithAuth<CacheStats>('/cache/stats');
  },

  // GAP-073: POST /cache/tune
  tune: async (config: {
    enabled?: boolean;
    similarity_threshold?: number;
    exact_ttl_seconds?: number;
    semantic_ttl_seconds?: number;
  }): Promise<void> => {
    await fetchWithAuth<void>('/cache/tune', {
      method: 'POST',
      body: JSON.stringify(config),
    });
  },

  // GAP-074: DELETE /cache/clear
  clear: async (): Promise<void> => {
    await fetchWithAuth<void>('/cache/clear', {
      method: 'DELETE',
    });
  },

  // GAP-075: POST /cache/evict (GAP-103 FIX: use query param not JSON body)
  evict: async (count?: number): Promise<{ evicted: number }> => {
    const queryCount = count ?? 100;
    return fetchWithAuth<{ evicted: number }>(`/cache/evict?count=${queryCount}`, {
      method: 'POST',
    });
  },

  // GET /cache/health
  getHealth: async (): Promise<{ status: string; message?: string }> => {
    return fetchWithAuth<{ status: string; message?: string }>('/cache/health');
  },

  // Legacy method - derives config from stats
  getConfig: async (): Promise<{
    enabled: boolean;
    similarity_threshold: number;
    ttl_seconds: number;
  }> => {
    const stats = await cacheApi.getStats();
    return {
      enabled: stats.config?.enabled ?? true,
      similarity_threshold: stats.config?.similarity_threshold ?? 0.85,
      ttl_seconds: stats.config?.exact_ttl_seconds ?? 3600,
    };
  },

  // Legacy method - maps to tune
  updateConfig: async (config: {
    enabled?: boolean;
    similarity_threshold?: number;
    ttl_seconds?: number;
  }): Promise<void> => {
    return cacheApi.tune({
      enabled: config.enabled,
      similarity_threshold: config.similarity_threshold,
      exact_ttl_seconds: config.ttl_seconds,
    });
  },
};

// Sandbox API - Real backend calls (GAP-076 through GAP-078)
export const sandboxApi = {
  // POST /sandbox/execute — run code in sandbox
  execute: async (request: CodeExecuteRequest): Promise<CodeExecuteResponse> => {
    return fetchWithAuth<CodeExecuteResponse>('/sandbox/execute', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  },

  // GAP-076: GET /sandbox/stats
  getStats: async (): Promise<SandboxStats> => {
    return fetchWithAuth<SandboxStats>('/sandbox/stats');
  },

  // GAP-077: POST /sandbox/config
  updateConfig: async (config: Partial<SandboxConfig>): Promise<SandboxConfig> => {
    const response = await fetchWithAuth<{
      message: string;
      updates: Record<string, unknown>;
      current_config: { enabled: boolean; total_tools: number; default_level: string };
      note: string;
    }>('/sandbox/config', {
      method: 'POST',
      body: JSON.stringify({ enabled: config.isolation_level !== 'none' }),
    });

    // Map backend response to frontend SandboxConfig shape
    return {
      isolation_level: (response.current_config.default_level as SandboxConfig['isolation_level']) || 'medium',
      timeout_seconds: config.timeout_seconds || 30,
      memory_limit_mb: config.memory_limit_mb || 256,
      allowed_tools: config.allowed_tools || [],
    };
  },

  // GAP-078: DELETE /sandbox/cache/clear
  clearCache: async (): Promise<void> => {
    await fetchWithAuth<void>('/sandbox/cache/clear', {
      method: 'DELETE',
    });
  },

  // GET /sandbox/health
  getHealth: async (): Promise<{ status: string; message?: string }> => {
    const response = await fetchWithAuth<{
      healthy: boolean;
      issues: string[] | null;
      sandbox: Record<string, unknown>;
      cache: Record<string, unknown>;
      timestamp: string;
    }>('/sandbox/health');

    return {
      status: response.healthy ? 'healthy' : 'unhealthy',
      message: response.issues?.join('; '),
    };
  },

  // GET /sandbox/tools
  getToolRegistry: async (): Promise<{
    tools: Array<{ name: string; isolation_level: string; agent: string }>;
  }> => {
    const response = await fetchWithAuth<{
      tools: Record<string, string>;
      by_isolation_level: Record<string, string[]>;
      total_tools: number;
      default_level: string;
    }>('/sandbox/tools');

    // Map backend response to frontend expected shape
    return {
      tools: Object.entries(response.tools).map(([name, level]) => ({
        name,
        isolation_level: level,
        agent: '', // Backend doesn't track agent per tool
      })),
    };
  },

  // Legacy method - derives config from stats
  getConfig: async (): Promise<SandboxConfig> => {
    const stats = await sandboxApi.getStats();
    return {
      isolation_level: (stats.registry?.default_level as SandboxConfig['isolation_level']) || 'medium',
      timeout_seconds: 30, // Not in stats, use default
      memory_limit_mb: 256, // Not in stats, use default
      allowed_tools: [], // Not in stats response
    };
  },
};

// Healing API - Real backend calls (GAP-079 through GAP-081)
export const healingApi = {
  // GAP-079: GET /healing/stats
  getStats: async (): Promise<{
    recoveries: number;
    failures: number;
    circuit_breakers_open: number;
  }> => {
    const response = await fetchWithAuth<{
      enabled: boolean;
      max_retry_attempts: number;
      circuit_breakers: Record<string, CircuitBreaker>;
      timestamp: string;
    }>('/healing/stats');

    // Transform to simpler frontend stats shape
    const openCount = Object.values(response.circuit_breakers).filter(
      (b) => b.state === 'open'
    ).length;

    return {
      recoveries: 0, // Not tracked in backend stats
      failures: Object.values(response.circuit_breakers).reduce(
        (sum, b) => sum + b.failure_count,
        0
      ),
      circuit_breakers_open: openCount,
    };
  },

  // GET /healing/circuit-breakers
  getCircuitBreakers: async (): Promise<{ breakers: CircuitBreaker[] }> => {
    const response = await fetchWithAuth<{
      total_circuits: number;
      circuits: Record<string, {
        name: string;
        state: 'closed' | 'open' | 'half_open';
        failure_count: number;
        failure_threshold: number;
        timeout_seconds: number;
        last_failure_time?: string;
        last_state_change?: string;
      }>;
      summary: { closed: number; open: number; half_open: number };
      timestamp: string;
    }>('/healing/circuit-breakers');

    // Map backend dict to frontend array
    const breakers: CircuitBreaker[] = Object.entries(response.circuits).map(
      ([name, breaker]) => ({
        name,
        state: breaker.state,
        failure_count: breaker.failure_count,
        failure_threshold: breaker.failure_threshold,
        timeout_seconds: breaker.timeout_seconds,
        last_failure: breaker.last_failure_time,
      })
    );

    return { breakers };
  },

  // GET /healing/circuit-breakers/{name}
  getCircuitBreaker: async (name: string): Promise<CircuitBreaker> => {
    const response = await fetchWithAuth<{
      name: string;
      state: 'closed' | 'open' | 'half_open';
      failure_count: number;
      failure_threshold: number;
      timeout_seconds: number;
      last_failure_time?: string;
      last_state_change?: string;
      timestamp: string;
    }>(`/healing/circuit-breakers/${name}`);

    return {
      name: response.name,
      state: response.state,
      failure_count: response.failure_count,
      failure_threshold: response.failure_threshold,
      timeout_seconds: response.timeout_seconds,
      last_failure: response.last_failure_time,
    };
  },

  // GAP-081: RESOLVED - Reset circuit breaker endpoint now exists
  // POST /healing/circuit-breakers/{name}/reset
  resetCircuitBreaker: async (name: string): Promise<CircuitBreaker> => {
    const response = await fetchWithAuth<{
      name: string;
      previous_state: string;
      new_state: 'closed' | 'open' | 'half_open';
      failure_count: number;
      message: string;
      timestamp: string;
    }>(`/healing/circuit-breakers/${name}/reset`, {
      method: 'POST',
    });

    return {
      name: response.name,
      state: response.new_state,
      failure_count: response.failure_count,
      failure_threshold: 5, // Default, not returned in reset response
      timeout_seconds: 60, // Default, not returned in reset response
      last_failure: undefined, // Reset clears failure state
    };
  },

  // GET /healing/health
  getHealth: async (): Promise<{ status: string; message?: string }> => {
    const response = await fetchWithAuth<{
      healthy: boolean;
      issues: string[] | null;
      self_healing: { enabled: boolean; max_retry_attempts: number };
      circuit_breakers: { total: number; closed: number; open: number; half_open: number };
      timestamp: string;
    }>('/healing/health');

    return {
      status: response.healthy ? 'healthy' : 'unhealthy',
      message: response.issues?.join('; '),
    };
  },

  // GAP-080: Note - /healing/config doesn't exist in backend
  // Would need backend addition for full config management
  getRetryConfig: async (): Promise<{
    max_retries: number;
    backoff_multiplier: number;
    max_backoff_seconds: number;
  }> => {
    // Return defaults since endpoint doesn't exist
    return {
      max_retries: 3,
      backoff_multiplier: 2,
      max_backoff_seconds: 60,
    };
  },

  updateRetryConfig: async (_config: {
    max_retries?: number;
    backoff_multiplier?: number;
  }): Promise<void> => {
    // GAP-080: Backend doesn't have this endpoint yet
    console.warn('Retry config update not supported - backend endpoint missing');
  },
};

// Safety API - Real backend calls (GAP-082, GAP-083, GAP-084)
export const safetyApi = {
  // GAP-082: GET /safety/violations
  getViolations: async (params?: {
    severity?: string;
    limit?: number;
  }): Promise<{ violations: SafetyViolation[]; total: number }> => {
    const searchParams = new URLSearchParams();
    if (params?.limit) searchParams.set('limit', String(params.limit));
    const query = searchParams.toString();

    const response = await fetchWithAuth<{
      validation_failures: Array<{
        model_type: string;
        route: string;
        errors: string[];
        timestamp: string;
      }>;
      sanitization_events: Array<{
        context: string;
        timestamp: string;
      }>;
      total_violations: number;
      time_period: string;
      error?: string;
    }>(`/safety/violations${query ? `?${query}` : ''}`);

    // Map backend response to frontend SafetyViolation shape
    const violations: SafetyViolation[] = [
      ...response.validation_failures.map((vf, idx) => ({
        id: `vf-${idx}`,
        timestamp: vf.timestamp,
        type: 'validation_failure' as const,
        details: vf.errors.join('; '),
        severity: 'medium' as const, // Backend doesn't track severity
      })),
      ...response.sanitization_events.map((se, idx) => ({
        id: `se-${idx}`,
        timestamp: se.timestamp,
        type: 'sanitization_event' as const,
        details: `Sanitization in ${se.context} context`,
        severity: 'low' as const,
      })),
    ];

    // Filter by severity if provided
    const filtered = params?.severity
      ? violations.filter((v) => v.severity === params.severity)
      : violations;

    return { violations: filtered, total: response.total_violations };
  },

  // GAP-083: GET /safety/stats
  getStats: async (): Promise<SafetyStats> => {
    const response = await fetchWithAuth<{
      validation_failures: number;
      sanitization_events: number;
      most_common_violations: Array<{ error: string; count: number }>;
      sanitization_by_context: Array<{
        context: string;
        total_events: number;
        avg_size_reduction: number;
      }>;
    }>('/safety/stats');

    return {
      validation_failures: response.validation_failures,
      sanitization_events: response.sanitization_events,
      most_common_violations: response.most_common_violations.map((v) => ({
        type: v.error,
        count: v.count,
      })),
      sanitization_by_context: response.sanitization_by_context.reduce(
        (acc, stat) => {
          acc[stat.context] = stat.total_events;
          return acc;
        },
        {} as Record<string, number>
      ),
    };
  },

  // GAP-084: GET /safety/sanitization_stats
  getSanitizationStats: async (): Promise<Record<string, number>> => {
    const response = await fetchWithAuth<{
      total_events: number;
      by_context: Record<string, number>;
      avg_size_reduction_pct: number;
      timestamp: string;
      error?: string;
    }>('/safety/sanitization_stats');

    return response.by_context;
  },

  // Legacy method - config not available in backend
  getConfig: async (): Promise<{
    input_validation: boolean;
    output_sanitization: boolean;
    pii_detection: boolean;
  }> => {
    // Not in backend API - return defaults
    return {
      input_validation: true,
      output_sanitization: true,
      pii_detection: true,
    };
  },
};

// Extension aggregate types
interface ExtensionStatusBackend {
  name: string;
  type: string;
  enabled: boolean;
  priority: number;
  health: 'healthy' | 'degraded' | 'down';
}

interface ExtensionMetricsBackend {
  cache_hit_rate: number;
  cache_savings_usd: number;
  sandbox_overhead_ms: number;
  healing_success_rate: number;
  threats_blocked: number;
  validation_failures: number;
  total_requests: number;
}

interface ExtensionTimelineEntry {
  timestamp: string;
  extension: string;
  event: string;
  duration_ms?: number;
}

interface ExtensionConfigBackend {
  extensions_enabled: boolean;
  input_validation_enabled: boolean;
  semantic_cache_enabled: boolean;
  self_healing_enabled: boolean;
  sandbox_enabled: boolean;
  file_safety_enabled: boolean;
  output_sanitization_enabled: boolean;
}

// Extensions API - Real backend calls
export const extensionsApi = {
  // GET /extensions/status
  getStatus: async (): Promise<ExtensionStatusBackend[]> => {
    return fetchWithAuth<ExtensionStatusBackend[]>('/extensions/status');
  },

  // GET /extensions/metrics
  getMetrics: async (): Promise<ExtensionMetricsBackend> => {
    return fetchWithAuth<ExtensionMetricsBackend>('/extensions/metrics');
  },

  // GET /extensions/timeline
  getTimeline: async (params?: {
    limit?: number;
    since?: string;
  }): Promise<ExtensionTimelineEntry[]> => {
    const searchParams = new URLSearchParams();
    if (params?.limit) searchParams.set('limit', String(params.limit));
    if (params?.since) searchParams.set('since', params.since);
    const query = searchParams.toString();

    return fetchWithAuth<ExtensionTimelineEntry[]>(
      `/extensions/timeline${query ? `?${query}` : ''}`
    );
  },

  // GET /extensions/config
  getConfig: async (): Promise<ExtensionConfigBackend> => {
    return fetchWithAuth<ExtensionConfigBackend>('/extensions/config');
  },
};
