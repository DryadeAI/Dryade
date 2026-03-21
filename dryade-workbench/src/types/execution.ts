// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// Workflow Execution Types for Dryade Platform
// Phase 66: Workflow Execution Visibility

// Execution status
export type ExecutionStatus = 'running' | 'completed' | 'failed' | 'cancelled';

// Node result within execution
export interface NodeResult {
  node_id: string;
  status: 'completed' | 'failed' | 'skipped';
  output?: unknown;
  duration_ms?: number;
  error?: string;
}

// Execution summary for lists
export interface ExecutionSummary {
  id: number;
  execution_id: string;
  scenario_name: string;
  status: ExecutionStatus;
  started_at: string;
  completed_at?: string;
  duration_ms?: number;
  source?: 'scenario' | 'plan';
  _plan_id?: number;  // For plan execution navigation
}

// Full execution details
export interface ExecutionDetail extends ExecutionSummary {
  user_id?: string;
  trigger_source: string;
  node_results: NodeResult[];
  final_result?: unknown;
  error?: string;
  inputs: Record<string, unknown>;
  created_at: string;
}

// SSE event types for real-time streaming
export interface WorkflowStartEvent {
  type: 'workflow_start';
  execution_id: string;
  scenario_name: string;
  trigger_source: string;
  timestamp: string;
}

export interface WorkflowNodesEvent {
  type: 'workflow_nodes';
  execution_id: string;
  nodes: Array<{ id: string; type: string }>;
  timestamp: string;
}

export interface NodeCompleteEvent {
  type: 'node_complete';
  execution_id: string;
  node_id: string;
  data: unknown;
  timestamp: string;
}

export interface WorkflowCompleteEvent {
  type: 'workflow_complete';
  execution_id: string;
  result: {
    output: unknown;
    executed_nodes: string[];
    state: Record<string, unknown>;
    error?: string;
  };
  timestamp: string;
}

export interface WorkflowErrorEvent {
  type: 'error';
  execution_id: string;
  error: string;
  timestamp: string;
}

export type WorkflowSSEEvent =
  | WorkflowStartEvent
  | WorkflowNodesEvent
  | NodeCompleteEvent
  | WorkflowCompleteEvent
  | WorkflowErrorEvent;
