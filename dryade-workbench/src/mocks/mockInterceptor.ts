// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// Mock interceptor - monkey-patches API modules to return static data
// To remove: delete this file and MockDataProvider.tsx

import * as api from '@/services/api';
import {
  mockUser, mockHealth, mockAgents, mockConversations, mockMessages,
  mockQueueStatus, mockLatencyStats, mockFlows, mockWorkflows,
  mockDashboardMetrics, mockPlugins, mockModeStats, mockRecentRequests,
  mockKnowledgeSources, mockModelsConfig, mockRegistryProviders,
} from './mockData';

// Store originals for restore
const originals: Record<string, Record<string, unknown>> = {};

function save(obj: Record<string, unknown>, key: string) {
  originals[key] = { ...obj };
}

function patch(obj: Record<string, unknown>, key: string, overrides: Record<string, unknown>) {
  save(obj, key);
  Object.assign(obj, overrides);
}

export function enableMocks() {
  const resolve = <T>(data: T) => () => Promise.resolve(data);

  patch(api.usersApi as unknown as Record<string, unknown>, 'usersApi', {
    getCurrentUser: resolve(mockUser),
  });

  patch(api.healthApi as unknown as Record<string, unknown>, 'healthApi', {
    getHealth: resolve(mockHealth),
    getDetailedHealth: resolve({ ...mockHealth, version: '1.5.0', uptime_seconds: 86400, environment: 'mock' }),
    getReady: resolve({ ready: true, message: 'Mock ready' }),
    getLive: resolve({ alive: true, timestamp: new Date().toISOString() }),
    getMetrics: resolve({ requests_total: 1847, errors_total: 12, uptime_seconds: 86400 }),
  });

  patch(api.agentsApi as unknown as Record<string, unknown>, 'agentsApi', {
    getAgents: resolve({ agents: mockAgents, total: mockAgents.length }),
    getAgent: (name: string) => Promise.resolve(mockAgents.find(a => a.name === name) || mockAgents[0]),
  });

  patch(api.chatApi as unknown as Record<string, unknown>, 'chatApi', {
    getConversations: resolve({ conversations: mockConversations, total: mockConversations.length, has_more: false }),
    getConversation: (id: string) => Promise.resolve(mockConversations.find(c => c.id === id) || mockConversations[0]),
    getMessages: (id: string) => Promise.resolve({ messages: mockMessages[id] || [], total: (mockMessages[id] || []).length, has_more: false }),
    createConversation: (_mode: string, title?: string) => Promise.resolve({ ...mockConversations[0], id: `conv-new-${Date.now()}`, title: title || 'New conversation' }),
    updateConversation: (id: string, updates: Record<string, unknown>) => Promise.resolve({ ...mockConversations[0], id, ...updates }),
    deleteConversation: resolve(undefined),
    bulkDeleteConversations: (ids: string[]) => Promise.resolve({ deleted_count: ids.length, failed_ids: [], message: 'Mock deleted' }),
    deleteAllConversations: resolve({ deleted_count: 3, message: 'Mock deleted all' }),
    addMessage: (_cid: string, content: string, role = 'user') => Promise.resolve({ id: `msg-${Date.now()}`, role, content, cached: false, created_at: new Date().toISOString() }),
    getStreamStatus: resolve({ active: false }),
    shareConversation: resolve(undefined),
    unshareConversation: resolve(undefined),
    cancelOrchestration: resolve(undefined),
  });

  patch(api.queueApi as unknown as Record<string, unknown>, 'queueApi', {
    getStatus: resolve(mockQueueStatus),
  });

  patch(api.metricsApi as unknown as Record<string, unknown>, 'metricsApi', {
    getLatency: resolve(mockLatencyStats),
    getDashboard: resolve(mockDashboardMetrics),
    getLatencyByMode: resolve(mockModeStats),
    getLatencyRecent: resolve(mockRecentRequests),
  });

  patch(api.flowsApi as unknown as Record<string, unknown>, 'flowsApi', {
    getFlows: resolve({ flows: mockFlows, total: mockFlows.length }),
  });

  patch(api.workflowsApi as unknown as Record<string, unknown>, 'workflowsApi', {
    getWorkflows: resolve(mockWorkflows),
  });

  patch(api.pluginsApi as unknown as Record<string, unknown>, 'pluginsApi', {
    getPlugins: resolve(mockPlugins),
    togglePlugin: (name: string, enabled: boolean) => {
      const plugin = mockPlugins.plugins.find(p => p.name === name);
      return Promise.resolve(plugin ? { ...plugin, status: enabled ? 'enabled' : 'disabled', enabled } : { name, enabled, status: enabled ? 'enabled' : 'disabled' });
    },
  });

  patch(api.knowledgeApi as unknown as Record<string, unknown>, 'knowledgeApi', {
    getSources: resolve(mockKnowledgeSources),
    search: resolve({ results: [], total: 0 }),
    deleteSource: resolve(undefined),
  });

  // Settings page APIs
  patch(api.modelsConfigApi as unknown as Record<string, unknown>, 'modelsConfigApi', {
    getConfig: resolve(mockModelsConfig),
    getProviders: resolve([
      { name: 'openai', display_name: 'OpenAI', models: ['gpt-4o', 'gpt-4o-mini', 'gpt-3.5-turbo'], requires_api_key: true, capabilities: ['llm', 'embedding', 'audio', 'vision'] },
      { name: 'anthropic', display_name: 'Anthropic', models: ['claude-3-opus', 'claude-3-sonnet', 'claude-3-haiku'], requires_api_key: true, capabilities: ['llm', 'vision'] },
    ]),
    getApiKeys: resolve([
      { provider: 'openai', is_set: true, masked_key: 'sk-...abc' },
    ]),
    updateConfig: (_cap: string, config: Record<string, unknown>) => Promise.resolve({ ...mockModelsConfig, ...config }),
    storeApiKey: resolve(undefined),
    deleteApiKey: resolve(undefined),
  });

  patch(api.providerRegistryApi as unknown as Record<string, unknown>, 'providerRegistryApi', {
    listProviders: resolve(mockRegistryProviders),
    discoverModels: (_provider: string) => Promise.resolve({ models: ['gpt-4o', 'gpt-4o-mini'], provider: _provider }),
    testConnection: (_provider: string) => Promise.resolve({ success: true, message: 'Mock connection OK', models: ['gpt-4o'] }),
  });

  patch(api.customProvidersApi as unknown as Record<string, unknown>, 'customProvidersApi', {
    create: resolve({ name: 'custom', display_name: 'Custom' }),
    delete: resolve(undefined),
  });

  // Mock remaining APIs that pages might call
  patch(api.executionsApi as unknown as Record<string, unknown>, 'executionsApi', {
    getExecutions: resolve({ executions: [], total: 0, has_more: false }),
  });

  patch(api.plansApi as unknown as Record<string, unknown>, 'plansApi', {
    getPlans: resolve({ plans: [], total: 0 }),
  });

  patch(api.extensionsApi as unknown as Record<string, unknown>, 'extensionsApi', {
    getStatus: resolve([]),
  });

  patch(api.projectsApi as unknown as Record<string, unknown>, 'projectsApi', {
    getProjects: resolve({ projects: [], total: 0 }),
    createProject: (data: { name: string }) => Promise.resolve({ id: `proj-${Date.now()}`, name: data.name, description: null, icon: null, color: null, is_archived: false, conversation_count: 0, created_at: new Date().toISOString(), updated_at: new Date().toISOString() }),
    updateProject: (id: string, data: Record<string, unknown>) => Promise.resolve({ id, name: 'Project', ...data, created_at: new Date().toISOString(), updated_at: new Date().toISOString() }),
    deleteProject: resolve(undefined),
    moveConversationToProject: resolve(undefined),
    deleteProjectConversations: resolve({ deleted_count: 0, message: 'Mock' }),
  });

  console.log('[Mock] API mocks enabled');
}

export function disableMocks() {
  for (const [key, original] of Object.entries(originals)) {
    const target = (api as unknown as Record<string, Record<string, unknown>>)[key];
    if (target && original) Object.assign(target, original);
  }
  if (Object.keys(originals).length) { Object.keys(originals).forEach(k => delete originals[k]); }
  console.log('[Mock] API mocks disabled');
}
