// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// API Types for Dryade Platform
// These are placeholders for future API integration

// Auth Types
export interface AuthUser {
  id: string;
  email: string;
  display_name?: string;
  avatar_url?: string;
  role: 'user' | 'admin';
  is_active: boolean;
  is_verified: boolean;
  is_external: boolean;
  preferences?: Record<string, unknown>;
  first_seen: string;
  last_seen: string;
  created_at: string;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  display_name?: string;
}

// Health Types
export interface HealthStatus {
  status: 'healthy' | 'degraded' | 'unhealthy';
  components: ComponentStatus[];
  timestamp: string;
}

export interface ComponentStatus {
  name: string;
  status: 'healthy' | 'degraded' | 'unhealthy';
  category: 'critical' | 'important' | 'optional';
  latency_ms?: number;
  message?: string;
}

export interface DetailedHealth extends HealthStatus {
  version: string;
  uptime_seconds: number;
  environment: string;
}

// Dashboard Types
export interface DashboardMetrics {
  total_requests: number;
  total_cost: number;
  avg_latency_ms: number;
  cache_hit_rate: number;
  period: string;
}

export interface QueueStatus {
  active: number;
  queued: number;
  rejected_total: number;
  max_concurrent: number;
  max_queue_size: number;
  average_wait_ms: number;
  status: 'healthy' | 'busy' | 'overloaded';
}

// Project Types
export interface Project {
  id: string;
  name: string;
  description: string | null;
  icon: string | null;  // Emoji or icon name
  color: string | null;  // Hex color like #3B82F6
  is_archived: boolean;
  conversation_count: number;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreate {
  name: string;
  description?: string;
  icon?: string;
  color?: string;
}

export interface ProjectUpdate {
  name?: string;
  description?: string;
  icon?: string;
  color?: string;
  is_archived?: boolean;
}

// Conversation Types
// Phase 85: Simplified to 2 modes. Chat (default, orchestrator-backed) and Planner.
export type ChatMode = 'chat' | 'planner';

// Options for streaming chat messages
export interface StreamOptions {
  verbose?: boolean;
  memory?: boolean;
  /** Enable LLM reasoning/thinking mode for models that support it (vLLM thinking models, Claude extended thinking) */
  enable_thinking?: boolean;
}

export interface Conversation {
  id: string;
  title: string | null;
  mode: ChatMode;
  status: 'active' | 'archived';
  message_count: number;
  project_id: string | null;  // Project assignment
  created_at: string;
  updated_at: string;
  // Additional fields from backend (GAP-024)
  user_id?: string;
  shared_with?: Array<{ user_id: string; permission: 'view' | 'edit' }>;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  tool_calls?: ToolCall[];
  cached: boolean;
  created_at: string;
  // Thinking/reasoning text for assistant messages
  thinking?: string;
  // Additional fields from backend (GAP-023)
  mode?: ChatMode;
  usage?: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
  exports?: {
    plan_id?: number;
    workflow_id?: number;
    flow_execution_id?: string;
  };
}

// Pagination params type (GAP-024)
export interface PaginationParams {
  limit?: number;
  offset?: number;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  offset: number;
  limit: number;
  has_more: boolean;
}

export interface ToolCall {
  tool: string;
  args: Record<string, unknown>;
  result?: string;
  status: 'pending' | 'executing' | 'complete' | 'error';
  duration_ms?: number;
}

// Agent Types
export type AgentFramework = 'crewai' | 'langchain' | 'adk' | 'a2a' | 'mcp' | 'custom';

/**
 * Agent type - Frontend representation
 *
 * Note: Backend AgentInfo does NOT have an 'id' field.
 * GAP-029: Frontend uses 'name' as 'id' for consistency.
 * GAP-038: Extra fields (tags, role, goal, backstory) are frontend-only or future backend fields.
 */
export interface Agent {
  id: string; // Will be same as name (backend doesn't provide id) - GAP-029
  name: string;
  description: string;
  framework: AgentFramework;
  tool_count: number;
  version: string;
  tags: string[]; // Frontend-only, not from backend - GAP-038
  // Optional fields that may come from backend in future
  role?: string;
  goal?: string;
  backstory?: string;
  metadata?: Record<string, unknown>;
}

export interface AgentTool {
  name: string;
  description: string;
  parameters: {
    type: 'object';
    properties: Record<string, {
      type: string;
      description?: string;
      required?: boolean;
    }>;
    required?: string[];
  };
}

export interface AgentDetail extends Agent {
  tools: AgentTool[];
}

export interface AgentInvokeRequest {
  task: string;
  context?: Record<string, unknown>;
}

/**
 * Agent invocation response
 * GAP-033: tokens_used and cost are required (derived from backend usage object)
 */
export interface AgentInvokeResponse {
  result: string;
  tool_calls: {
    tool: string;
    args: Record<string, unknown>;
    result: string;
    duration_ms: number;
  }[];
  execution_time_ms: number;
  tokens_used: number; // GAP-033: from backend usage.total_tokens
  cost: number; // GAP-033: from backend usage.cost
}

// Flow Types
export type FlowStatus = 'idle' | 'running' | 'complete' | 'error';
export type FlowNodeType = 'start' | 'task' | 'router' | 'end';
export type FlowNodeStatus = 'pending' | 'running' | 'complete' | 'error' | 'skipped';

export interface Flow {
  id: string;
  name: string;
  description?: string;
  status: FlowStatus;
  node_count: number;
  last_run?: string;
  last_execution_id?: string;
  entry_point?: string; // GAP-035: Flow entry point from backend
}

export interface FlowNode {
  id: string;
  type: FlowNodeType;
  label: string;
  description?: string;
  agent?: string;
  task?: string;
  position: { x: number; y: number };
  status?: FlowNodeStatus;
}

export interface FlowEdge {
  id: string;
  source: string;
  target: string;
  label?: string;
  animated?: boolean;
}

export interface FlowDetail extends Flow {
  nodes: FlowNode[];
  edges: FlowEdge[];
  metadata?: Record<string, unknown>;
}

export interface FlowExecution {
  id: string;
  flow_name: string;
  status: 'running' | 'complete' | 'error' | 'cancelled';
  started_at: string;
  completed_at?: string;
  duration_ms?: number;
  total_cost?: number;
  node_results: {
    node_id: string;
    node_name: string;
    status: FlowNodeStatus;
    output?: string;
    error?: string;
    duration_ms?: number;
  }[];
  checkpoints: FlowCheckpoint[];
}

export interface FlowCheckpoint {
  id: string;
  node_id: string;
  node_name: string;
  created_at: string;
  state?: Record<string, unknown>;
}

// Cost Types
export interface CostSummary {
  total_cost: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_requests: number;
  period_start: string;
  period_end: string;
}

export interface CostRecord {
  id: string;
  timestamp: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  cost: number;
  conversation_id?: string;
  user_id?: string;
  agent_name?: string;
}
