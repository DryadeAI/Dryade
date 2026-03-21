/**
 * Reusable workflow schema constants for E2E tests.
 *
 * Each schema is a valid WorkflowSchema JSON matching the backend format:
 * { version, nodes[], edges[], metadata? }
 *
 * Node types match the backend enum: start, task, router, end, tool, approval
 * Node data varies by type: task nodes have { agent, task }, router nodes
 * have { condition }, approval nodes have { prompt, approver }.
 */

/**
 * Backend-compatible workflow JSON shape.
 * Mirrors dryade-core/core/workflows/schema.py WorkflowSchema.
 */
export interface WorkflowSchemaJson {
  version: string;
  nodes: WorkflowNodeJson[];
  edges: WorkflowEdgeJson[];
  metadata?: Record<string, unknown>;
}

export interface WorkflowNodeJson {
  id: string;
  type: "start" | "task" | "router" | "end" | "tool" | "approval";
  data: Record<string, unknown>;
  position: { x: number; y: number };
  metadata?: {
    label?: string;
    description?: string;
    tags?: string[];
  };
}

export interface WorkflowEdgeJson {
  id: string;
  source: string;
  target: string;
  type?: string;
  data?: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// 1. LINEAR_WORKFLOW: start -> task_1 -> end (3 nodes, 2 edges)
// ---------------------------------------------------------------------------
export const LINEAR_WORKFLOW: WorkflowSchemaJson = {
  version: "1.0.0",
  nodes: [
    {
      id: "start",
      type: "start",
      data: {},
      position: { x: 0, y: 0 },
      metadata: { label: "Start" },
    },
    {
      id: "task_1",
      type: "task",
      data: {
        agent: "default",
        task: "Summarize the input data and return a brief overview.",
      },
      position: { x: 250, y: 0 },
      metadata: { label: "Summarize", description: "Summarize input data" },
    },
    {
      id: "end",
      type: "end",
      data: {},
      position: { x: 500, y: 0 },
      metadata: { label: "End" },
    },
  ],
  edges: [
    { id: "e-start-task1", source: "start", target: "task_1" },
    { id: "e-task1-end", source: "task_1", target: "end" },
  ],
  metadata: { description: "Simple linear workflow for E2E testing" },
};

// ---------------------------------------------------------------------------
// 2. BRANCHING_WORKFLOW: start -> [task_a, task_b] -> end (4 nodes, 4 edges)
//    Diamond/fan-out shape
// ---------------------------------------------------------------------------
export const BRANCHING_WORKFLOW: WorkflowSchemaJson = {
  version: "1.0.0",
  nodes: [
    {
      id: "start",
      type: "start",
      data: {},
      position: { x: 0, y: 100 },
      metadata: { label: "Start" },
    },
    {
      id: "task_a",
      type: "task",
      data: {
        agent: "default",
        task: "Analyze the data from a technical perspective.",
      },
      position: { x: 250, y: 0 },
      metadata: { label: "Technical Analysis" },
    },
    {
      id: "task_b",
      type: "task",
      data: {
        agent: "default",
        task: "Analyze the data from a business perspective.",
      },
      position: { x: 250, y: 200 },
      metadata: { label: "Business Analysis" },
    },
    {
      id: "end",
      type: "end",
      data: {},
      position: { x: 500, y: 100 },
      metadata: { label: "End" },
    },
  ],
  edges: [
    { id: "e-start-a", source: "start", target: "task_a" },
    { id: "e-start-b", source: "start", target: "task_b" },
    { id: "e-a-end", source: "task_a", target: "end" },
    { id: "e-b-end", source: "task_b", target: "end" },
  ],
  metadata: { description: "Diamond branching workflow for E2E testing" },
};

// ---------------------------------------------------------------------------
// 3. CONDITIONAL_WORKFLOW: start -> condition -> [true_task, false_task] -> end
//    (5 nodes, 4 edges -- condition node with data.condition expression)
// ---------------------------------------------------------------------------
export const CONDITIONAL_WORKFLOW: WorkflowSchemaJson = {
  version: "1.0.0",
  nodes: [
    {
      id: "start",
      type: "start",
      data: {},
      position: { x: 0, y: 100 },
      metadata: { label: "Start" },
    },
    {
      id: "condition_1",
      type: "router",
      data: {
        condition: "state.get('priority', 'low') == 'high'",
        branches: [
          { condition: "true", target: "true_task" },
          { condition: "false", target: "false_task" },
        ],
      },
      position: { x: 250, y: 100 },
      metadata: { label: "Priority Check", description: "Route by priority level" },
    },
    {
      id: "true_task",
      type: "task",
      data: {
        agent: "default",
        task: "Handle high-priority item with detailed analysis.",
      },
      position: { x: 500, y: 0 },
      metadata: { label: "High Priority Handler" },
    },
    {
      id: "false_task",
      type: "task",
      data: {
        agent: "default",
        task: "Handle low-priority item with standard processing.",
      },
      position: { x: 500, y: 200 },
      metadata: { label: "Standard Handler" },
    },
    {
      id: "end",
      type: "end",
      data: {},
      position: { x: 750, y: 100 },
      metadata: { label: "End" },
    },
  ],
  edges: [
    { id: "e-start-cond", source: "start", target: "condition_1" },
    {
      id: "e-cond-true",
      source: "condition_1",
      target: "true_task",
      data: { condition: "true" },
    },
    {
      id: "e-cond-false",
      source: "condition_1",
      target: "false_task",
      data: { condition: "false" },
    },
    { id: "e-true-end", source: "true_task", target: "end" },
  ],
  metadata: {
    description: "Conditional routing workflow for E2E testing",
  },
};

// ---------------------------------------------------------------------------
// 4. APPROVAL_WORKFLOW: start -> task_1 -> approval -> task_2 -> end
//    (5 nodes, 4 edges -- approval node with prompt/approver in data)
// ---------------------------------------------------------------------------
export const APPROVAL_WORKFLOW: WorkflowSchemaJson = {
  version: "1.0.0",
  nodes: [
    {
      id: "start",
      type: "start",
      data: {},
      position: { x: 0, y: 0 },
      metadata: { label: "Start" },
    },
    {
      id: "task_1",
      type: "task",
      data: {
        agent: "default",
        task: "Draft a proposal document based on the input requirements.",
      },
      position: { x: 250, y: 0 },
      metadata: { label: "Draft Proposal" },
    },
    {
      id: "approval_1",
      type: "approval",
      data: {
        prompt: "Review and approve the drafted proposal before proceeding.",
        approver: "owner",
        display_fields: ["proposal_text"],
        timeout_seconds: 3600,
        timeout_action: "reject",
      },
      position: { x: 500, y: 0 },
      metadata: {
        label: "Manager Approval",
        description: "Requires manager approval to continue",
      },
    },
    {
      id: "task_2",
      type: "task",
      data: {
        agent: "default",
        task: "Finalize the proposal after approval and prepare for submission.",
      },
      position: { x: 750, y: 0 },
      metadata: { label: "Finalize Proposal" },
    },
    {
      id: "end",
      type: "end",
      data: {},
      position: { x: 1000, y: 0 },
      metadata: { label: "End" },
    },
  ],
  edges: [
    { id: "e-start-task1", source: "start", target: "task_1" },
    { id: "e-task1-approval", source: "task_1", target: "approval_1" },
    { id: "e-approval-task2", source: "approval_1", target: "task_2" },
    { id: "e-task2-end", source: "task_2", target: "end" },
  ],
  metadata: {
    description: "Approval gate workflow for E2E testing",
  },
};

// ---------------------------------------------------------------------------
// 5. LONG_LINEAR_WORKFLOW: start -> task_1 -> task_2 -> task_3 -> task_4 -> end
//    (6 nodes, 5 edges -- for zigzag layout testing)
// ---------------------------------------------------------------------------
export const LONG_LINEAR_WORKFLOW: WorkflowSchemaJson = {
  version: "1.0.0",
  nodes: [
    {
      id: "start",
      type: "start",
      data: {},
      position: { x: 0, y: 0 },
      metadata: { label: "Start" },
    },
    {
      id: "task_1",
      type: "task",
      data: {
        agent: "default",
        task: "Collect raw data from all configured sources.",
      },
      position: { x: 250, y: 0 },
      metadata: { label: "Data Collection" },
    },
    {
      id: "task_2",
      type: "task",
      data: {
        agent: "default",
        task: "Clean and normalize the collected data for analysis.",
      },
      position: { x: 500, y: 0 },
      metadata: { label: "Data Cleaning" },
    },
    {
      id: "task_3",
      type: "task",
      data: {
        agent: "default",
        task: "Run statistical analysis and generate insights.",
      },
      position: { x: 750, y: 0 },
      metadata: { label: "Analysis" },
    },
    {
      id: "task_4",
      type: "task",
      data: {
        agent: "default",
        task: "Generate a formatted report with charts and recommendations.",
      },
      position: { x: 1000, y: 0 },
      metadata: { label: "Report Generation" },
    },
    {
      id: "end",
      type: "end",
      data: {},
      position: { x: 1250, y: 0 },
      metadata: { label: "End" },
    },
  ],
  edges: [
    { id: "e-start-task1", source: "start", target: "task_1" },
    { id: "e-task1-task2", source: "task_1", target: "task_2" },
    { id: "e-task2-task3", source: "task_2", target: "task_3" },
    { id: "e-task3-task4", source: "task_3", target: "task_4" },
    { id: "e-task4-end", source: "task_4", target: "end" },
  ],
  metadata: {
    description: "Long linear workflow for zigzag layout testing",
  },
};
