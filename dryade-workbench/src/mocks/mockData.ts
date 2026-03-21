// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// Centralized mock data for UI testing without backend
// To remove: delete this file, mockInterceptor.ts, MockDataProvider.tsx,
// remove MockDataProvider from App.tsx

import type { HealthStatus, QueueStatus, AuthUser, Agent, Conversation, ChatMessage } from '@/types/api';
import type { Flow } from '@/types/api';

export const mockUser: AuthUser = {
  id: 'mock-user-001',
  email: 'demo@dryade.ai',
  display_name: 'Demo User',
  avatar_url: undefined,
  role: 'admin',
  is_active: true,
  is_verified: true,
  is_external: false,
  preferences: {},
  first_seen: '2025-01-15T10:00:00Z',
  last_seen: new Date().toISOString(),
  created_at: '2025-01-15T10:00:00Z',
};

export const mockHealth: HealthStatus = {
  status: 'healthy',
  components: [
    { name: 'database', status: 'healthy', category: 'critical', latency_ms: 2 },
    { name: 'redis', status: 'healthy', category: 'critical', latency_ms: 1 },
    { name: 'llm_provider', status: 'healthy', category: 'important', latency_ms: 45 },
    { name: 'vector_store', status: 'healthy', category: 'optional', latency_ms: 8 },
  ],
  timestamp: new Date().toISOString(),
};

export const mockAgents: Agent[] = [
  {
    id: 'research-assistant', name: 'research-assistant', description: 'Searches the web and synthesizes information into structured reports.',
    framework: 'langchain', tool_count: 5, version: '1.2.0', tags: ['research', 'web'],
  },
  {
    id: 'code-reviewer', name: 'code-reviewer', description: 'Analyzes code for bugs, security issues, and best practices.',
    framework: 'crewai', tool_count: 3, version: '2.0.1', tags: ['code', 'review'],
  },
  {
    id: 'data-analyst', name: 'data-analyst', description: 'Processes datasets and generates visual insights and summaries.',
    framework: 'custom', tool_count: 7, version: '0.9.0', tags: ['data', 'analytics'],
  },
  {
    id: 'task-planner', name: 'task-planner', description: 'Breaks complex goals into actionable task sequences with dependencies.',
    framework: 'adk', tool_count: 4, version: '1.0.0', tags: ['planning', 'orchestration'],
  },
];

export const mockConversations: Conversation[] = [
  {
    id: 'conv-001', title: 'Project architecture review', mode: 'chat', status: 'active',
    message_count: 12, project_id: null, created_at: '2025-02-08T14:00:00Z', updated_at: '2025-02-09T09:30:00Z',
  },
  {
    id: 'conv-002', title: 'Sprint planning Q1', mode: 'planner', status: 'active',
    message_count: 8, project_id: null, created_at: '2025-02-07T10:00:00Z', updated_at: '2025-02-08T16:00:00Z',
  },
  {
    id: 'conv-003', title: 'API integration troubleshooting', mode: 'chat', status: 'active',
    message_count: 24, project_id: null, created_at: '2025-02-05T08:00:00Z', updated_at: '2025-02-06T11:00:00Z',
  },
];

export const mockMessages: Record<string, ChatMessage[]> = {
  'conv-001': [
    { id: 'msg-1', role: 'user', content: 'Can you review our microservices architecture?', cached: false, created_at: '2025-02-08T14:00:00Z' },
    { id: 'msg-2', role: 'assistant', content: 'I\'d be happy to review your architecture. Let me analyze the service boundaries, communication patterns, and data flow. Here are my findings:\n\n1. **Service Decomposition**: Your services are well-bounded around domain contexts.\n2. **Communication**: Consider switching from synchronous REST to async messaging for non-critical paths.\n3. **Data**: Each service owns its data store — good pattern.', cached: false, created_at: '2025-02-08T14:01:00Z' },
  ],
};

export const mockQueueStatus: QueueStatus = {
  active: 2,
  queued: 5,
  rejected_total: 0,
  max_concurrent: 10,
  max_queue_size: 100,
  average_wait_ms: 320,
  status: 'healthy',
};

export const mockLatencyStats = {
  avg_ms: 245,
  p50_ms: 180,
  p95_ms: 520,
  p99_ms: 890,
  total_requests: 1847,
};

export const mockFlows: Flow[] = [
  {
    id: 'flow-001', name: 'Customer Onboarding', description: 'Automated customer onboarding workflow with verification steps.',
    status: 'idle' as const, node_count: 6, last_run: '2025-02-09T12:00:00Z',
  },
  {
    id: 'flow-002', name: 'Data Pipeline', description: 'ETL pipeline for daily report generation.',
    status: 'complete' as const, node_count: 4, last_run: '2025-02-10T06:00:00Z',
  },
];

export const mockWorkflows = {
  workflows: [
    { id: 'wf-001', name: 'Research Pipeline', description: 'Multi-agent research and summarization', status: 'draft', node_count: 5, version: '1.0.0', execution_count: 42, created_at: '2025-02-01T10:00:00Z', updated_at: '2025-02-09T15:00:00Z' },
    { id: 'wf-002', name: 'Code Review Flow', description: 'Automated PR review with multiple checks', status: 'published', node_count: 8, version: '2.1.0', execution_count: 187, created_at: '2025-01-20T08:00:00Z', updated_at: '2025-02-08T12:00:00Z' },
  ],
  total: 2,
};

export const mockDashboardMetrics = {
  total_requests: 1847,
  total_cost: 12.45,
  avg_latency_ms: 245,
  cache_hit_rate: 0.73,
  period: 'last_24h',
};

export const mockModeStats = [
  { mode: 'chat', request_count: 1200, avg_latency_ms: 220, p95_latency_ms: 480, success_rate: 0.97 },
  { mode: 'planner', request_count: 420, avg_latency_ms: 380, p95_latency_ms: 720, success_rate: 0.94 },
  { mode: 'agent', request_count: 227, avg_latency_ms: 310, p95_latency_ms: 650, success_rate: 0.91 },
];

export const mockRecentRequests = [
  { id: 'req-001', mode: 'chat', status: 'success', latency_ms: 180, tokens: 450, timestamp: '2025-02-10T08:55:00Z', model: 'gpt-4o' },
  { id: 'req-002', mode: 'planner', status: 'success', latency_ms: 320, tokens: 820, timestamp: '2025-02-10T08:50:00Z', model: 'gpt-4o' },
  { id: 'req-003', mode: 'chat', status: 'error', latency_ms: 510, tokens: 0, timestamp: '2025-02-10T08:45:00Z', model: 'gpt-4o', error_message: 'Rate limit exceeded' },
  { id: 'req-004', mode: 'agent', status: 'success', latency_ms: 240, tokens: 600, timestamp: '2025-02-10T08:40:00Z', model: 'claude-3' },
  { id: 'req-005', mode: 'chat', status: 'success', latency_ms: 150, tokens: 300, timestamp: '2025-02-10T08:35:00Z', model: 'gpt-4o' },
];

export const mockKnowledgeSources = {
  sources: [
    { id: 'ks-001', name: 'Product Documentation', source_type: 'pdf', status: 'ready', chunk_count: 142, size_bytes: 2450000, crews: ['Data Team'], agents: ['research-assistant'], created_at: '2025-01-20T10:00:00Z', updated_at: '2025-02-05T14:00:00Z' },
    { id: 'ks-002', name: 'API Reference', source_type: 'md', status: 'ready', chunk_count: 89, size_bytes: 560000, crews: [], agents: ['code-reviewer'], created_at: '2025-01-25T08:00:00Z', updated_at: '2025-02-08T11:00:00Z' },
  ],
  total: 2,
};

export const mockPlugins = {
  plugins: [
    { name: 'cost_tracker', display_name: 'Cost Tracker', version: '1.0.0', enabled: true, status: 'enabled' as const, health: 'healthy' as const, category: 'pipeline' as const, has_config: true, description: 'Track LLM usage costs', author: 'dryade' },
    { name: 'file_safety', display_name: 'File Safety', version: '1.0.0', enabled: true, status: 'enabled' as const, health: 'healthy' as const, category: 'backend' as const, has_config: false, description: 'File operation safety checks', author: 'dryade' },
  ],
  total: 2,
};

export const mockModelsConfig = {
  llm: { provider: 'openai', model: 'gpt-4o' },
  embedding: { provider: 'openai', model: 'text-embedding-3-small' },
  audio: { provider: 'openai', model: 'whisper-1' },
  vision: { provider: 'openai', model: 'gpt-4o' },
  llm_endpoint: null,
  asr_endpoint: null,
};

export const mockRegistryProviders = [
  { name: 'openai', display_name: 'OpenAI', requires_api_key: true, supports_custom_endpoint: false, is_custom: false, base_url: null, capabilities: { llm: true, embedding: true, audio_asr: true, audio_tts: true, vision: true } },
  { name: 'anthropic', display_name: 'Anthropic', requires_api_key: true, supports_custom_endpoint: false, is_custom: false, base_url: null, capabilities: { llm: true, embedding: false, audio_asr: false, audio_tts: false, vision: true } },
];
