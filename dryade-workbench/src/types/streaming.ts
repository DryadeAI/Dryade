// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
/**
 * Agent streaming event types for crew mode execution visibility.
 * These map to SSE events emitted by core/crew/event_bridge.py
 */

// Base chunk type (extends existing StreamChunk pattern)
export interface AgentStreamChunkBase {
  timestamp?: string;
}

// Agent execution lifecycle
export interface AgentStartChunk extends AgentStreamChunkBase {
  type: 'agent_start';
  agent: string;      // Agent role name
  task?: string;      // Current task description
}

export interface AgentCompleteChunk extends AgentStreamChunkBase {
  type: 'agent_complete';
  agent: string;
  result?: string;
  error?: string;
}

// Thinking/reasoning stream
export interface ThinkingChunk extends AgentStreamChunkBase {
  type: 'thinking';
  agent: string;
  content: string;    // Markdown content to stream
}

// Tool usage
export interface ToolStartChunk extends AgentStreamChunkBase {
  type: 'tool_start';
  agent: string;
  tool: string;
  args?: Record<string, unknown>;
}

export interface ToolCompleteChunk extends AgentStreamChunkBase {
  type: 'tool_complete';
  agent: string;
  tool: string;
  result?: string;
  error?: string;
}

// Clarification request (human-in-the-loop)
export interface ClarifyChunk extends AgentStreamChunkBase {
  type: 'clarify';
  question: string;
  options: string[];
  context?: Record<string, unknown>;
}

// Escalation request (orchestrator needs user decision)
export interface EscalationChunk extends AgentStreamChunkBase {
  type: 'escalation';
  content: string;      // The question for the user
  task_context?: string; // What task failed
  inline?: boolean;     // Display inline in chat (default true)
  has_auto_fix?: boolean; // Whether automatic fix is available on approval
}

// Reasoning event (orchestrator reasoning visibility)
export interface ReasoningChunk extends AgentStreamChunkBase {
  type: 'reasoning';
  content: string;      // Summary text
  detailed?: string;    // Full reasoning (expandable)
  visibility?: 'summary' | 'detailed' | 'hidden';
}

// Rich orchestration events (Phase 82)
export interface PlanPreviewChunk extends AgentStreamChunkBase {
  type: 'plan_preview';
  content: string;
  steps: Array<{ agent: string; task: string; depends_on?: string[] }>;
  step_count: number;
  estimated_duration_s?: number;
}

export interface PlanEditChunk extends AgentStreamChunkBase {
  type: 'plan_edit';
  step_index: number;
  action: 'add' | 'remove' | 'modify';
  new_step?: { agent: string; task: string };
}

export interface ProgressChunk extends AgentStreamChunkBase {
  type: 'progress';
  content: string;
  current_step: number;
  total_steps: number;
  percentage: number;
  eta_seconds?: number;
  current_agent: string;
}

export interface CostUpdateChunk extends AgentStreamChunkBase {
  type: 'cost_update';
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  estimated_cost_usd?: number;
}

export interface ArtifactChunk extends AgentStreamChunkBase {
  type: 'artifact';
  content: string;
  name: string;
  mime_type: string;
  size_bytes: number;
  preview?: string;
}

export interface AgentRetryChunk extends AgentStreamChunkBase {
  type: 'agent_retry';
  content: string;
  agent: string;
  attempt: number;
  max_attempts: number;
  error: string;
  wait_seconds: number;
}

export interface AgentFallbackChunk extends AgentStreamChunkBase {
  type: 'agent_fallback';
  content: string;
  original_agent: string;
  fallback_agent: string;
  reason: string;
}

export interface CancelAckChunk extends AgentStreamChunkBase {
  type: 'cancel_ack';
  content: string;
  partial_results_count: number;
  current_step?: number;
  reason: string;
}

export interface MemoryUpdateChunk extends AgentStreamChunkBase {
  type: 'memory_update';
  content: string;
  key: string;
  value_preview: string;
  scope: 'session' | 'persistent';
}

// Union type for all agent stream chunks
export type AgentStreamChunk =
  | AgentStartChunk
  | AgentCompleteChunk
  | ThinkingChunk
  | ToolStartChunk
  | ToolCompleteChunk
  | ClarifyChunk
  | EscalationChunk
  | ReasoningChunk
  | PlanPreviewChunk
  | PlanEditChunk
  | ProgressChunk
  | CostUpdateChunk
  | ArtifactChunk
  | AgentRetryChunk
  | AgentFallbackChunk
  | CancelAckChunk
  | MemoryUpdateChunk;

// Type guard functions
export function isAgentChunk(chunk: unknown): chunk is AgentStreamChunk {
  if (!chunk || typeof chunk !== 'object') return false;
  const c = chunk as { type?: string };
  return [
    'agent_start', 'agent_complete', 'thinking',
    'tool_start', 'tool_complete',
    'clarify', 'escalation', 'reasoning',
    'plan_preview', 'plan_edit', 'progress',
    'cost_update', 'artifact',
    'agent_retry', 'agent_fallback',
    'cancel_ack', 'memory_update',
  ].includes(c.type ?? '');
}

export function isEscalationChunk(chunk: unknown): chunk is EscalationChunk {
  if (!chunk || typeof chunk !== 'object') return false;
  return (chunk as { type?: string }).type === 'escalation';
}

