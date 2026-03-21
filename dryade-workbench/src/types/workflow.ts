// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// Workflow types aligned with backend schema

export type WorkflowNodeType = 'start' | 'task' | 'router' | 'tool' | 'end' | 'approval';
export type WorkflowStatus = 'draft' | 'published' | 'archived';

// UI-specific node types for visual editor
export type NodeType = 'input' | 'output' | 'agent' | 'decision' | 'start' | 'task' | 'router' | 'tool' | 'end' | 'approval';

// Node runtime status (UI state during execution)
export type NodeStatus = 'idle' | 'pending' | 'running' | 'success' | 'complete' | 'error' | 'skipped' | 'awaiting_approval';

// Approval node configuration (mirrors backend ApprovalNodeData)
export interface ApprovalNodeConfig {
  prompt: string;
  approver: 'owner' | 'specific_user' | 'any_member';
  approver_user_id?: string;
  display_fields: string[];
  timeout_seconds: number;
  timeout_action: 'approve' | 'reject' | 'escalate';
  // Runtime fields (set by backend during execution)
  approval_request_id?: number;
  runtime_status?: 'awaiting_approval' | 'approved' | 'rejected';
  state_values?: Record<string, unknown>;
}

// Execution event from SSE stream for workflow log display
export interface ExecutionEvent {
  type: 'workflow_start' | 'node_start' | 'node_complete' | 'checkpoint' | 'error' | 'workflow_complete' | 'start' | 'complete' | 'approval_pending' | 'approval_resolved';
  timestamp: string;
  execution_id?: number;
  node_id?: string;
  message?: string;
  output?: unknown;
  error?: string;
  duration_ms?: number;
  checkpoint_id?: string;
  // Approval-specific fields
  approval_request_id?: number;
  workflow_id?: number;
  workflow_name?: string;
  prompt?: string;
}

export interface WorkflowNode {
  id: string;
  type: WorkflowNodeType | NodeType; // Accept both backend and UI types
  label: string;
  description?: string;
  agent?: string;
  task?: string;
  tool?: string;                          // Explicit MCP tool name
  arguments?: Record<string, unknown>;    // Tool arguments (JSON)
  position: { x: number; y: number };
  // Runtime status (not persisted)
  status?: NodeStatus;
  outputs?: string[]; // Runtime execution outputs
  // Node-specific config (e.g. approval runtime state: approval_request_id)
  config?: Record<string, unknown>;
}

export interface WorkflowEdge {
  id: string;
  source: string; // NOT 'from'
  target: string; // NOT 'to'
  label?: string;
  condition?: string;
  animated?: boolean; // ReactFlow display prop
}

// Legacy Connection type for WorkflowPage compatibility
// Uses 'from'/'to' instead of 'source'/'target'
export interface Connection {
  id: string;
  from: string;
  to: string;
}

export interface WorkflowSchema {
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  version: string; // semver e.g. "1.0.0"
  metadata?: Record<string, unknown>;
}

export interface Workflow {
  id: number; // int, NOT string
  name: string;
  description?: string;
  version: string; // semver
  status: WorkflowStatus;
  is_public: boolean;
  user_id?: string;
  tags?: string[];
  execution_count?: number;
  published_at?: string;
  created_at: string;
  updated_at: string;
  workflow_json: WorkflowSchema;
}

export interface WorkflowListItem {
  id: number;
  name: string;
  description?: string;
  version: string;
  status: WorkflowStatus;
  is_public: boolean;
  execution_count: number;
  created_at: string;
  updated_at: string;
}

export interface WorkflowValidation {
  valid: boolean;
  errors: ValidationError[];
  warnings: ValidationWarning[];
}

export interface ValidationError {
  node_id?: string;
  message: string;
  type: 'missing_connection' | 'invalid_config' | 'cycle_detected' | 'orphan_node';
}

export interface ValidationWarning {
  node_id?: string;
  message: string;
  type: 'unused_output' | 'long_chain' | 'missing_description';
}

// Helper to convert ReactFlow nodes/edges to backend format
export function toBackendWorkflow(
  nodes: WorkflowNode[],
  edges: WorkflowEdge[]
): WorkflowSchema {
  return {
    nodes: nodes.map(({ status: _status, outputs: _outputs, config: _config, ...node }) => node), // Remove runtime fields
    edges: edges.map(({ animated, ...edge }) => edge), // Remove display props
    version: '1.0.0',
  };
}

// Helper to convert backend workflow to ReactFlow format
export function fromBackendWorkflow(
  workflow: Workflow
): { nodes: WorkflowNode[]; edges: WorkflowEdge[] } {
  return {
    nodes: workflow.workflow_json.nodes,
    edges: workflow.workflow_json.edges,
  };
}
