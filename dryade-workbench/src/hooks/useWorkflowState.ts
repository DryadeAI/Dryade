// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
/**
 * useWorkflowState - Extracted from WorkflowPage.tsx (Phase 117-07)
 *
 * Contains all state management, handler functions, and side effects
 * for the workflow editor page. WorkflowPage becomes a thin composition layer.
 */
import { useState, useCallback, useEffect, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { type WorkflowNode, type Connection, type NodeType, type WorkflowNodeType, type ExecutionEvent } from "@/types/workflow";
import { type WorkflowStatus } from "@/components/workflow/WorkflowHeader";
import { toast } from "sonner";
import { scenariosApi, plansApi, workflowsApi } from "@/services/api";
import type { WorkflowListItem } from "@/services/api";
import {
  useWorkflows,
  useCreateWorkflow,
  useDeleteWorkflow,
  usePublishWorkflow,
  useArchiveWorkflow,
} from "@/hooks/useApi";
import { fetchStream } from "@/services/apiClient";
import type { ScenarioInfo, ScenarioWorkflowGraph, ScenarioWorkflowNode, ScenarioInputSchema, Plan } from "@/types/extended-api";

// ---------------------------------------------------------------------------
// Utility functions (moved from WorkflowPage.tsx)
// ---------------------------------------------------------------------------

/** Convert scenario workflow node to frontend WorkflowNode */
function scenarioNodeToWorkflowNode(node: ScenarioWorkflowNode): WorkflowNode {
  const validTypes: WorkflowNodeType[] = ['start', 'task', 'router', 'tool', 'end'];
  const nodeType = validTypes.includes(node.type as WorkflowNodeType)
    ? (node.type as WorkflowNodeType)
    : 'task';

  let label = node.metadata?.label || node.metadata?.description?.split('.')[0];
  if (!label && node.data?.agent) {
    label = node.data.agent.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  }
  if (!label) {
    label = node.type.charAt(0).toUpperCase() + node.type.slice(1);
  }

  return {
    id: node.id,
    type: nodeType,
    label,
    description: node.data?.task || node.metadata?.description,
    agent: node.data?.agent,
    task: node.data?.task,
    position: node.position,
    status: 'idle',
  };
}

/** Convert scenario workflow to frontend format */
function convertScenarioWorkflow(workflow: ScenarioWorkflowGraph): {
  nodes: WorkflowNode[];
  connections: Connection[];
} {
  const nodes = Array.isArray(workflow?.nodes) ? workflow.nodes.map(scenarioNodeToWorkflowNode) : [];
  const connections: Connection[] = Array.isArray(workflow?.edges) ? workflow.edges.map(edge => ({
    id: edge.id,
    from: edge.source,
    to: edge.target,
  })) : [];
  return { nodes, connections };
}

import { layoutGraph } from "@/utils/layoutGraph";

const WORKFLOW_LAYOUT_CONFIG = {
  direction: 'horizontal' as const,
  nodeWidth: 220,
  nodeHeight: 120,
  hSpacing: 100,
  vSpacing: 60,
  startX: 100,
  startY: 80,
};

function calculateTopologicalLayout(
  nodeIds: string[],
  edges: Array<{ from?: string; to?: string; source?: string; target?: string }>
): Map<string, { x: number; y: number }> {
  return layoutGraph(nodeIds, edges, WORKFLOW_LAYOUT_CONFIG);
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface CanvasState {
  nodes: WorkflowNode[];
  connections: Connection[];
}

interface ClipboardData {
  nodes: WorkflowNode[];
}

/** Unified workflow item for dropdown */
export interface UnifiedWorkflowItem {
  id: string;
  name: string;
  displayName: string;
  description: string;
  type: 'scenario' | 'plan';
  domain?: string;
  createdAt?: string;
  scenario?: ScenarioInfo;
  plan?: Plan;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const defaultNodes: WorkflowNode[] = [
  {
    id: "node-1",
    type: "input",
    label: "Data Source",
    description: "Fetch data from API endpoint",
    position: { x: 200, y: 200 },
    status: "idle",
  },
  {
    id: "node-2",
    type: "agent",
    label: "AI Processor",
    description: "Analyze and transform data",
    position: { x: 450, y: 200 },
    status: "idle",
  },
  {
    id: "node-3",
    type: "decision",
    label: "Validation",
    description: "Check data quality threshold",
    position: { x: 700, y: 200 },
    status: "idle",
  },
  {
    id: "node-4",
    type: "output",
    label: "Export Results",
    description: "Save to database",
    position: { x: 950, y: 200 },
    status: "idle",
  },
];

const defaultConnections: Connection[] = [
  { id: "conn-1", from: "node-1", to: "node-2" },
  { id: "conn-2", from: "node-2", to: "node-3" },
  { id: "conn-3", from: "node-3", to: "node-4" },
];

/** Keyboard shortcuts configuration */
export const shortcuts = [
  { keys: ["Cmd", "Enter"], action: "Run workflow" },
  { keys: ["Esc"], action: "Stop" },
  { keys: ["Cmd", "S"], action: "Save" },
  { keys: ["Cmd", "Z"], action: "Undo" },
  { keys: ["Cmd", "Shift", "Z"], action: "Redo" },
  { keys: ["Cmd", "C"], action: "Copy nodes" },
  { keys: ["Cmd", "V"], action: "Paste nodes" },
  { keys: ["Cmd", "D"], action: "Duplicate" },
  { keys: ["Cmd", "A"], action: "Select all" },
  { keys: ["Del"], action: "Delete node" },
];

// SessionStorage keys for view state persistence
const WF_STORAGE = {
  selectedWorkflowId: 'dryade-wf-selectedWorkflowId',
  selectedPlanId: 'dryade-wf-selectedPlanId',
  currentWorkflowId: 'dryade-wf-currentWorkflowId',
  workflowStatus: 'dryade-wf-status',
  executionId: 'dryade-wf-executionId',
  executionEvents: 'dryade-wf-events',
  workflowResult: 'dryade-wf-result',
} as const;

function ssGet(key: string): string | null {
  try { return sessionStorage.getItem(key); } catch { return null; }
}
function ssSet(key: string, value: string): void {
  try { sessionStorage.setItem(key, value); } catch { /* quota exceeded */ }
}
function ssRemove(key: string): void {
  try { sessionStorage.removeItem(key); } catch { /* ignore */ }
}

// ---------------------------------------------------------------------------
// Helpers: inject synthetic start/end nodes (GAP-P1)
// ---------------------------------------------------------------------------

function injectStartEndNodes(
  taskNodes: WorkflowNode[],
  loadedConns: Connection[]
): { allNodes: WorkflowNode[]; allEdges: Connection[] } {
  const targetSet = new Set(loadedConns.map(e => e.to));
  const sourceSet = new Set(loadedConns.map(e => e.from));
  const rootNodeIds = taskNodes.filter(n => !targetSet.has(n.id)).map(n => n.id);
  const leafNodeIds = taskNodes.filter(n => !sourceSet.has(n.id)).map(n => n.id);

  const startNode: WorkflowNode = {
    id: 'start-node',
    type: 'start',
    label: 'Start',
    position: { x: 400, y: 0 },
    status: 'idle',
  };
  const maxY = Math.max(...taskNodes.map(n => n.position?.y ?? 0), 0);
  const endNode: WorkflowNode = {
    id: 'end-node',
    type: 'end',
    label: 'End',
    position: { x: 400, y: maxY + 200 },
    status: 'idle',
  };

  const startEdges: Connection[] = rootNodeIds.map(rootId => ({
    id: `start-to-${rootId}`,
    from: startNode.id,
    to: rootId,
  }));
  const endEdges: Connection[] = leafNodeIds.map(leafId => ({
    id: `${leafId}-to-end`,
    from: leafId,
    to: endNode.id,
  }));

  return {
    allNodes: [startNode, ...taskNodes, endNode],
    allEdges: [...startEdges, ...loadedConns, ...endEdges],
  };
}

// ---------------------------------------------------------------------------
// Hook return type
// ---------------------------------------------------------------------------

export interface WorkflowState {
  // URL params
  searchParams: URLSearchParams;
  setSearchParams: ReturnType<typeof useSearchParams>[1];

  // Workflow library state
  workflows: ScenarioInfo[];
  userPlans: Plan[];
  workflowsLoading: boolean;
  selectedWorkflowId: string | null;
  selectedWorkflow: ScenarioInfo | null;
  selectedPlan: Plan | null;
  isAIGenerated: boolean;

  // Canvas state
  nodes: WorkflowNode[];
  connections: Connection[];
  selectedNodeIds: string[];
  setSelectedNodeIds: React.Dispatch<React.SetStateAction<string[]>>;
  selectedNode: WorkflowNode | null;
  runningNodeId: string | null;
  isRunning: boolean;
  workflowStatus: WorkflowStatus;
  currentStep: number;
  totalSteps: number;
  validateOnRun: boolean;
  setValidateOnRun: (v: boolean) => void;
  sidebarWidth: number;
  setSidebarWidth: (w: number) => void;
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (v: boolean) => void;
  executionId: string | number | null;
  workflowResult: unknown;

  // Input modal
  inputModalOpen: boolean;
  setInputModalOpen: (open: boolean) => void;
  scenarioInputs: ScenarioInputSchema[];

  // Backend plan status
  backendPlanStatus: string | null;

  // Result modal
  resultModalOpen: boolean;
  setResultModalOpen: (open: boolean) => void;

  // Execution log
  executionEvents: ExecutionEvent[];
  logCollapsed: boolean;
  setLogCollapsed: (collapsed: boolean) => void;

  // Clipboard
  clipboard: ClipboardData | null;

  // Undo/Redo
  canUndo: boolean;
  canRedo: boolean;

  // Template provenance (GAP-T2)
  sourceTemplateId: number | null;
  setSourceTemplateId: (id: number | null) => void;
  sourceTemplateVersionId: number | null;
  setSourceTemplateVersionId: (id: number | null) => void;

  // Dirty state
  isDirty: boolean;
  setIsDirty: (dirty: boolean) => void;
  initialLoadComplete: React.MutableRefObject<boolean>;

  // Delete confirmation
  deleteDialogOpen: boolean;
  setDeleteDialogOpen: (open: boolean) => void;
  isDeleting: boolean;

  // Create workflow dialog (GAP-W5)
  showCreateDialog: boolean;
  setShowCreateDialog: (show: boolean) => void;
  newWorkflowName: string;
  setNewWorkflowName: (name: string) => void;
  newWorkflowDescription: string;
  setNewWorkflowDescription: (desc: string) => void;
  isCreating: boolean;

  // Custom workflow (GAP-W6)
  currentWorkflowId: number | null;

  // GAP-W8: React Query workflows
  myWorkflows: WorkflowListItem[];
  loadingMyWorkflows: boolean;
  refetchWorkflows: () => void;
  publishWorkflowMutation: ReturnType<typeof usePublishWorkflow>;
  archiveWorkflowMutation: ReturnType<typeof useArchiveWorkflow>;
  deleteWorkflowMutation: ReturnType<typeof useDeleteWorkflow>;

  // GAP-W9: Share workflow
  showShareDialog: boolean;
  setShowShareDialog: (show: boolean) => void;
  shareEmail: string;
  setShareEmail: (email: string) => void;
  sharePermission: 'view' | 'edit';
  setSharePermission: (perm: 'view' | 'edit') => void;
  currentShares: Array<{ user_id: string; permission: string }>;
  shareError: string | null;

  // HITL approval
  pendingApproval: {
    approval_request_id: number;
    workflow_id: number;
    workflow_name: string;
    node_id: string;
    prompt: string;
  } | null;
  clearPendingApproval: () => void;

  // Handlers
  handleUndo: () => void;
  handleRedo: () => void;
  handleSelectWorkflow: (workflow: ScenarioInfo) => void;
  handleSelectPlan: (plan: Plan) => void;
  handleCreateWorkflow: () => void;
  handleAddNode: (type: NodeType) => void;
  handleUpdateNode: (id: string, updates: Partial<WorkflowNode>) => void;
  handleNodesChange: (newNodes: WorkflowNode[]) => void;
  handleConnectionsChange: (newConnections: Connection[]) => void;
  handleDeleteNode: (id: string) => void;
  handleDeleteWorkflow: () => Promise<void>;
  handleOpenShare: () => Promise<void>;
  handleShare: () => Promise<void>;
  handleUnshare: (userId: string) => Promise<void>;
  handleCopyNodes: (ids: string[]) => void;
  handlePasteNodes: (position: { x: number; y: number }) => void;
  handleDuplicateNodes: (ids: string[]) => void;
  handleSelectAll: () => void;
  handleOpenNodeProperties: (id: string) => void;
  handleRunWorkflow: () => Promise<void>;
  handleInputSubmit: (values: Record<string, unknown>, files: Record<string, File>) => void;
  handleRunNode: (id: string) => Promise<void>;
  handleStopWorkflow: () => Promise<void>;
  handleSave: () => Promise<void>;
  handleSaveAsTemplate: () => void;
  handleResetWorkflow: () => void;
  handleResetStuckPlan: () => Promise<void>;
  handlePlanLoaded: (planId: number, planNodes: WorkflowNode[], planEdges: { from: string; to: string }[]) => void;
  loadWorkflowById: (workflowId: number) => Promise<void>;
  handleCreateWorkflowSubmit: () => Promise<void>;
  handleDeleteCustomWorkflow: (workflowId: number) => Promise<void>;
  handlePublishCustomWorkflow: () => Promise<void>;
  handleArchiveCustomWorkflow: () => Promise<void>;
}

// ---------------------------------------------------------------------------
// Hook implementation
// ---------------------------------------------------------------------------

export function useWorkflowState(): WorkflowState {
  const [searchParams, setSearchParams] = useSearchParams();

  // Workflow library state
  const [workflows, setWorkflows] = useState<ScenarioInfo[]>([]);
  const [userPlans, setUserPlans] = useState<Plan[]>([]);
  const [workflowsLoading, setWorkflowsLoading] = useState(true);
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string | null>(ssGet(WF_STORAGE.selectedWorkflowId));
  const [selectedWorkflow, setSelectedWorkflow] = useState<ScenarioInfo | null>(null);
  const [selectedPlan, setSelectedPlan] = useState<Plan | null>(null);
  const [isAIGenerated, setIsAIGenerated] = useState(false);

  // Canvas state
  const [nodes, setNodes] = useState<WorkflowNode[]>(defaultNodes);
  const [connections, setConnections] = useState<Connection[]>(defaultConnections);
  const [selectedNodeIds, setSelectedNodeIds] = useState<string[]>([]);
  const [runningNodeId, setRunningNodeId] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const isRunningRef = useRef(false);
  const [workflowStatus, setWorkflowStatus] = useState<WorkflowStatus>((ssGet(WF_STORAGE.workflowStatus) as WorkflowStatus) || "idle");
  const [currentStep, setCurrentStep] = useState<number>(0);
  const [validateOnRun, setValidateOnRun] = useState(true);
  const [sidebarWidth, setSidebarWidth] = useState(320);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [executionId, setExecutionId] = useState<string | number | null>(ssGet(WF_STORAGE.executionId));
  const [workflowResult, setWorkflowResult] = useState<unknown>(() => {
    try { return JSON.parse(ssGet(WF_STORAGE.workflowResult) || 'null'); } catch { return null; }
  });

  // Input modal
  const [inputModalOpen, setInputModalOpen] = useState(false);
  const [scenarioInputs, setScenarioInputs] = useState<ScenarioInputSchema[]>([]);
  const [pendingInputs, setPendingInputs] = useState<Record<string, unknown>>({});

  // HITL approval state
  const [pendingApproval, setPendingApproval] = useState<{
    approval_request_id: number;
    workflow_id: number;
    workflow_name: string;
    node_id: string;
    prompt: string;
  } | null>(null);
  const clearPendingApproval = useCallback(() => setPendingApproval(null), []);

  // Backend plan status
  const [backendPlanStatus, setBackendPlanStatus] = useState<string | null>(null);

  // Result modal
  const [resultModalOpen, setResultModalOpen] = useState(false);

  // Execution log
  const [executionEvents, setExecutionEvents] = useState<ExecutionEvent[]>(() => {
    try { return JSON.parse(ssGet(WF_STORAGE.executionEvents) || '[]'); } catch { return []; }
  });
  const [logCollapsed, setLogCollapsed] = useState(false);

  // Clipboard
  const [clipboard, setClipboard] = useState<ClipboardData | null>(null);

  // Undo/Redo
  const [history, setHistory] = useState<CanvasState[]>([{ nodes: defaultNodes, connections: defaultConnections }]);
  const [historyIndex, setHistoryIndex] = useState(0);
  const isUndoRedoAction = useRef(false);
  const lastDeletedNodes = useRef<{ nodes: WorkflowNode[]; connections: Connection[] } | null>(null);

  // Template provenance (GAP-T2)
  const [sourceTemplateId, setSourceTemplateId] = useState<number | null>(null);
  const [sourceTemplateVersionId, setSourceTemplateVersionId] = useState<number | null>(null);

  // Dirty state
  const [isDirty, setIsDirty] = useState(false);
  const initialLoadComplete = useRef(false);

  // Delete confirmation
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  // Create workflow dialog (GAP-W5)
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [newWorkflowName, setNewWorkflowName] = useState('');
  const [newWorkflowDescription, setNewWorkflowDescription] = useState('');
  const [isCreating, setIsCreating] = useState(false);

  // Custom workflow (GAP-W6)
  const [currentWorkflowId, setCurrentWorkflowId] = useState<number | null>(null);

  // GAP-W8: React Query hooks
  const { data: workflowsData, isLoading: loadingMyWorkflows, refetch: refetchWorkflows } = useWorkflows();
  const myWorkflows = workflowsData?.workflows ?? [];
  const createWorkflowMutation = useCreateWorkflow();
  const deleteWorkflowMutation = useDeleteWorkflow();
  const publishWorkflowMutation = usePublishWorkflow();
  const archiveWorkflowMutation = useArchiveWorkflow();

  // GAP-W9: Share state
  const [showShareDialog, setShowShareDialog] = useState(false);
  const [shareEmail, setShareEmail] = useState('');
  const [sharePermission, setSharePermission] = useState<'view' | 'edit'>('view');
  const [currentShares, setCurrentShares] = useState<Array<{ user_id: string; permission: string }>>([]);
  const [shareError, setShareError] = useState<string | null>(null);

  // Derived state
  const selectedNode = selectedNodeIds.length === 1
    ? nodes.find((n) => n.id === selectedNodeIds[0]) || null
    : null;
  const totalSteps = nodes.length;
  const canUndo = historyIndex > 0;
  const canRedo = historyIndex < history.length - 1;

  // -------------------------------------------------------------------------
  // History / Undo / Redo
  // -------------------------------------------------------------------------

  const pushHistory = useCallback((newNodes: WorkflowNode[], newConnections: Connection[]) => {
    if (isUndoRedoAction.current) {
      isUndoRedoAction.current = false;
      return;
    }
    setHistory(prev => {
      const newHistory = prev.slice(0, historyIndex + 1);
      newHistory.push({ nodes: newNodes, connections: newConnections });
      if (newHistory.length > 50) {
        return newHistory.slice(-50);
      }
      return newHistory;
    });
    setHistoryIndex(prev => Math.min(prev + 1, 49));
  }, [historyIndex]);

  const handleUndo = useCallback(() => {
    if (!canUndo) return;
    isUndoRedoAction.current = true;
    const newIndex = historyIndex - 1;
    const state = history[newIndex];
    setNodes(state.nodes);
    setConnections(state.connections);
    setHistoryIndex(newIndex);
    toast.info("Undo", { duration: 1500 });
  }, [canUndo, historyIndex, history]);

  const handleRedo = useCallback(() => {
    if (!canRedo) return;
    isUndoRedoAction.current = true;
    const newIndex = historyIndex + 1;
    const state = history[newIndex];
    setNodes(state.nodes);
    setConnections(state.connections);
    setHistoryIndex(newIndex);
    toast.info("Redo", { duration: 1500 });
  }, [canRedo, historyIndex, history]);

  // -------------------------------------------------------------------------
  // SessionStorage persistence effects
  // -------------------------------------------------------------------------

  useEffect(() => {
    if (selectedWorkflowId) {
      ssSet(WF_STORAGE.selectedWorkflowId, selectedWorkflowId);
    } else {
      ssRemove(WF_STORAGE.selectedWorkflowId);
    }
  }, [selectedWorkflowId]);

  useEffect(() => {
    if (currentWorkflowId) {
      ssSet(WF_STORAGE.currentWorkflowId, String(currentWorkflowId));
    } else {
      ssRemove(WF_STORAGE.currentWorkflowId);
    }
  }, [currentWorkflowId]);

  useEffect(() => {
    ssSet(WF_STORAGE.workflowStatus, workflowStatus);
  }, [workflowStatus]);

  useEffect(() => {
    if (executionId) {
      ssSet(WF_STORAGE.executionId, String(executionId));
    } else {
      ssRemove(WF_STORAGE.executionId);
    }
  }, [executionId]);

  useEffect(() => {
    if (workflowResult) {
      ssSet(WF_STORAGE.workflowResult, JSON.stringify(workflowResult));
    } else {
      ssRemove(WF_STORAGE.workflowResult);
    }
  }, [workflowResult]);

  // Keep isRunningRef in sync (XR-001 fix)
  useEffect(() => {
    isRunningRef.current = isRunning;
  }, [isRunning]);

  // Validate stale "running" status on restore
  useEffect(() => {
    if (workflowStatus === "running" && !isRunning) {
      setWorkflowStatus("idle");
      ssSet(WF_STORAGE.workflowStatus, "idle");
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // -------------------------------------------------------------------------
  // Load workflows library on mount
  // -------------------------------------------------------------------------

  // eslint-disable-next-line @typescript-eslint/no-use-before-define
  const handleSelectPlan = useCallback(async (plan: Plan) => {
    setSelectedWorkflowId(null);
    setSelectedWorkflow(null);
    setSelectedPlan(plan);
    setCurrentWorkflowId(null);
    setWorkflowStatus("idle");
    setSelectedNodeIds([]);
    setExecutionEvents([]);
    setIsAIGenerated(true);
    setScenarioInputs([]);
    ssSet(WF_STORAGE.selectedPlanId, String(plan.id));
    ssRemove(WF_STORAGE.currentWorkflowId);
    ssRemove(WF_STORAGE.executionEvents);

    setSearchParams({ planId: String(plan.id) }, { replace: true });
    sessionStorage.setItem('lastPlanId', String(plan.id));

    const loadedConns: Connection[] = (plan.edges ?? []).map((edge) => ({
      id: `conn-${edge.source}-${edge.target}`,
      from: edge.source,
      to: edge.target,
    }));

    const nodeIds = (plan.nodes ?? []).map((n) => n.id);
    const positions = calculateTopologicalLayout(nodeIds, loadedConns);

    const taskNodes: WorkflowNode[] = (plan.nodes ?? []).map((node) => ({
      id: node.id,
      type: 'task' as WorkflowNodeType,
      label: node.agent || node.label || 'Task',
      description: node.description || '',
      agent: node.agent,
      task: node.description || node.task,
      tool: node.tool,
      arguments: node.arguments,
      position: positions.get(node.id) || { x: 100, y: 100 },
      status: 'idle' as const,
    }));

    const { allNodes, allEdges } = injectStartEndNodes(taskNodes, loadedConns);

    setNodes(allNodes);
    setConnections(allEdges);
    setHistory([{ nodes: allNodes, connections: allEdges }]);
    setHistoryIndex(0);
    setIsDirty(false);
    initialLoadComplete.current = true;
  }, [setSearchParams]);

  useEffect(() => {
    const planId = searchParams.get('planId');

    const loadWorkflowLibrary = async () => {
      setWorkflowsLoading(true);
      try {
        const [scenariosData, plansData] = await Promise.all([
          scenariosApi.listScenarios(),
          plansApi.getPlans({ limit: 50 }).catch(() => ({ plans: [] })),
        ]);

        setWorkflows(scenariosData);
        setUserPlans(plansData.plans || []);

        if (planId) {
          setWorkflowsLoading(false);
          return;
        }

        const restoredPlanId = ssGet(WF_STORAGE.selectedPlanId);
        const restoredWorkflowId = ssGet(WF_STORAGE.selectedWorkflowId);
        const restoredCustomId = ssGet(WF_STORAGE.currentWorkflowId);

        if (restoredCustomId) {
          try {
            const wfId = parseInt(restoredCustomId, 10);
            const workflow = await workflowsApi.getWorkflow(wfId);
            const wfJson = workflow.workflow_json;
            if (wfJson?.nodes) {
              const loadedNodes: WorkflowNode[] = wfJson.nodes.map((n) => ({
                id: n.id,
                type: (n.type as WorkflowNodeType) || 'task',
                label: n.label || 'Node',
                description: n.description,
                agent: n.agent,
                task: n.task,
                position: n.position || { x: 100, y: 100 },
                status: 'idle' as const,
              }));
              const loadedConns: Connection[] = (wfJson.edges || []).map((e) => ({
                id: e.id,
                from: e.source,
                to: e.target,
              }));
              setNodes(loadedNodes);
              setConnections(loadedConns);
              setHistory([{ nodes: loadedNodes, connections: loadedConns }]);
              setHistoryIndex(0);
            }
            setCurrentWorkflowId(wfId);
            setSelectedWorkflowId(null);
            setSelectedWorkflow(null);
            setSelectedPlan(null);
            setIsAIGenerated(false);
            setWorkflowStatus('idle');
            setIsDirty(false);
            setWorkflowsLoading(false);
            return;
          } catch {
            ssRemove(WF_STORAGE.currentWorkflowId);
          }
        }

        if (restoredPlanId) {
          const plan = (plansData.plans || []).find(p => String(p.id) === restoredPlanId);
          if (plan) {
            handleSelectPlan(plan);
            setWorkflowsLoading(false);
            return;
          }
        }

        if (restoredWorkflowId) {
          const scenario = scenariosData.find(s => s.name === restoredWorkflowId);
          if (scenario) {
            setSelectedWorkflowId(scenario.name);
            setSelectedWorkflow(scenario);
            setSelectedPlan(null);
            const workflowGraph = await scenariosApi.getWorkflow(scenario.name);
            const { nodes: loadedNodes, connections: loadedConns } = convertScenarioWorkflow(workflowGraph);
            setNodes(loadedNodes);
            setConnections(loadedConns);
            setHistory([{ nodes: loadedNodes, connections: loadedConns }]);
            setHistoryIndex(0);
            const detail = await scenariosApi.getScenario(scenario.name);
            setScenarioInputs(detail.inputs || []);
            setWorkflowsLoading(false);
            return;
          }
        }

        if (scenariosData.length > 0) {
          setSelectedWorkflowId(scenariosData[0].name);
          setSelectedWorkflow(scenariosData[0]);
          setSelectedPlan(null);
          const workflowGraph = await scenariosApi.getWorkflow(scenariosData[0].name);
          const { nodes: loadedNodes, connections: loadedConns } = convertScenarioWorkflow(workflowGraph);
          setNodes(loadedNodes);
          setConnections(loadedConns);
          setHistory([{ nodes: loadedNodes, connections: loadedConns }]);
          setHistoryIndex(0);
          const detail = await scenariosApi.getScenario(scenariosData[0].name);
          setScenarioInputs(detail.inputs || []);
        } else {
          setScenarioInputs([]);
        }
      } catch (error) {
        console.error("Failed to load workflow library:", error);
        toast.error("Failed to load workflows");
        setScenarioInputs([]);
      } finally {
        setWorkflowsLoading(false);
      }
    };
    loadWorkflowLibrary();
  }, [searchParams, handleSelectPlan]);

  // Load plan from URL param
  useEffect(() => {
    const planId = searchParams.get('planId');
    if (!planId) return;

    const loadPlan = async () => {
      setWorkflowsLoading(true);
      try {
        const plan = await plansApi.getPlan(Number(planId));
        setBackendPlanStatus(plan.status);

        const loadedConns: Connection[] = (plan.edges || []).map((edge, i) => ({
          id: edge.id || `edge-${i}`,
          from: edge.source,
          to: edge.target,
        }));

        const nodeIds = plan.nodes.map((n) => n.id);
        const positions = calculateTopologicalLayout(nodeIds, loadedConns);

        const taskNodes: WorkflowNode[] = plan.nodes.map((node) => ({
          id: node.id,
          type: node.type as WorkflowNodeType || 'task',
          label: node.label || node.agent || 'Task',
          description: node.description,
          agent: node.agent,
          task: node.description,
          tool: node.tool,
          arguments: node.arguments,
          position: positions.get(node.id) || { x: 100, y: 100 },
          status: 'idle',
        }));

        const { allNodes, allEdges } = injectStartEndNodes(taskNodes, loadedConns);

        setNodes(allNodes);
        setConnections(allEdges);
        setHistory([{ nodes: allNodes, connections: allEdges }]);
        setHistoryIndex(0);
        setIsAIGenerated(true);
        setSelectedWorkflowId(null);
        setSelectedWorkflow(null);

        sessionStorage.setItem('lastPlanId', planId);
        toast.success(`Loaded plan: ${plan.name}`);
      } catch (error) {
        console.error("Failed to load plan:", error);
        toast.error("Failed to load plan from URL");
        setIsAIGenerated(false);
      } finally {
        setWorkflowsLoading(false);
      }
    };

    loadPlan();
  }, [searchParams]);

  // -------------------------------------------------------------------------
  // Workflow / Plan selection handlers
  // -------------------------------------------------------------------------

  const handleSelectWorkflow = useCallback(async (workflow: ScenarioInfo) => {
    const currentPlanId = searchParams.get('planId');

    if (currentPlanId && isDirty) {
      const confirmed = window.confirm(
        "You have unsaved changes to your AI-generated plan. Switch to scenario anyway?"
      );
      if (!confirmed) return;
    }

    setSelectedWorkflowId(workflow.name);
    setSelectedWorkflow(workflow);
    setSelectedPlan(null);
    setCurrentWorkflowId(null);
    setWorkflowStatus("idle");
    setSelectedNodeIds([]);
    setExecutionEvents([]);
    setIsAIGenerated(false);
    setSourceTemplateId(null);
    setSourceTemplateVersionId(null);
    ssRemove(WF_STORAGE.selectedPlanId);
    ssRemove(WF_STORAGE.currentWorkflowId);
    ssRemove(WF_STORAGE.executionEvents);

    if (currentPlanId) {
      setSearchParams({}, { replace: true });
      sessionStorage.removeItem('lastPlanId');
    }

    try {
      const workflowGraph = await scenariosApi.getWorkflow(workflow.name);
      const { nodes: loadedNodes, connections: loadedConns } = convertScenarioWorkflow(workflowGraph);
      setNodes(loadedNodes);
      setConnections(loadedConns);
      setHistory([{ nodes: loadedNodes, connections: loadedConns }]);
      setHistoryIndex(0);

      const detail = await scenariosApi.getScenario(workflow.name);
      setScenarioInputs(detail.inputs || []);
    } catch (error) {
      console.error("Failed to load workflow:", error);
      toast.error("Failed to load workflow");
      setNodes([]);
      setConnections([]);
      setHistory([{ nodes: [], connections: [] }]);
      setHistoryIndex(0);
      setScenarioInputs([]);
    }
  }, [searchParams, isDirty, setSearchParams]);

  const handleCreateWorkflow = useCallback(() => {
    setShowCreateDialog(true);
  }, []);

  // -------------------------------------------------------------------------
  // Node manipulation handlers
  // -------------------------------------------------------------------------

  const handleAddNode = useCallback((type: NodeType) => {
    const newNode: WorkflowNode = {
      id: `node-${Date.now()}`,
      type,
      label: `New ${type.charAt(0).toUpperCase() + type.slice(1)}`,
      position: { x: 400 + Math.random() * 200, y: 300 + Math.random() * 100 },
      status: "idle",
    };
    const newNodes = [...nodes, newNode];
    setNodes(newNodes);
    pushHistory(newNodes, connections);
    setSelectedNodeIds([newNode.id]);
    toast.success(`Added ${type} node`);
  }, [nodes, connections, pushHistory]);

  const handleUpdateNode = useCallback(
    (id: string, updates: Partial<WorkflowNode>) => {
      const newNodes = nodes.map((node) => (node.id === id ? { ...node, ...updates } : node));
      setNodes(newNodes);
      if (!('status' in updates) && !('outputs' in updates)) {
        pushHistory(newNodes, connections);
      }
    },
    [nodes, connections, pushHistory]
  );

  const handleNodesChange = useCallback((newNodes: WorkflowNode[]) => {
    setNodes(newNodes);
  }, []);

  const handleConnectionsChange = useCallback((newConnections: Connection[]) => {
    setConnections(newConnections);
    pushHistory(nodes, newConnections);
  }, [nodes, pushHistory]);

  const handleDeleteNode = useCallback(
    (id: string) => {
      const nodeToDelete = nodes.find(n => n.id === id);
      const connectionsToDelete = connections.filter(c => c.from === id || c.to === id);

      if (nodeToDelete) {
        lastDeletedNodes.current = { nodes: [nodeToDelete], connections: connectionsToDelete };
      }

      const newNodes = nodes.filter((node) => node.id !== id);
      const newConnections = connections.filter((conn) => conn.from !== id && conn.to !== id);

      setNodes(newNodes);
      setConnections(newConnections);
      pushHistory(newNodes, newConnections);

      setSelectedNodeIds((prev) => prev.filter((nodeId) => nodeId !== id));

      toast.success("Node deleted", {
        action: {
          label: "Undo",
          onClick: () => {
            if (lastDeletedNodes.current) {
              const { nodes: deletedNodes, connections: deletedConns } = lastDeletedNodes.current;
              const restoredNodes = [...newNodes, ...deletedNodes];
              const restoredConnections = [...newConnections, ...deletedConns];
              setNodes(restoredNodes);
              setConnections(restoredConnections);
              pushHistory(restoredNodes, restoredConnections);
              toast.info("Node restored");
            }
          },
        },
        duration: 5000,
      });
    },
    [nodes, connections, pushHistory]
  );

  // -------------------------------------------------------------------------
  // Workflow deletion
  // -------------------------------------------------------------------------

  const handleDeleteWorkflow = useCallback(async () => {
    if (!selectedPlan) {
      toast.error("No plan selected to delete");
      return;
    }

    setIsDeleting(true);
    try {
      await plansApi.deletePlan(selectedPlan.id);

      setNodes(defaultNodes);
      setConnections(defaultConnections);
      setHistory([{ nodes: defaultNodes, connections: defaultConnections }]);
      setHistoryIndex(0);
      setSelectedPlan(null);
      setIsAIGenerated(false);
      setWorkflowStatus("idle");
      setWorkflowResult(null);
      setExecutionEvents([]);

      const newParams = new URLSearchParams(searchParams);
      newParams.delete('planId');
      setSearchParams(newParams);

      setUserPlans(prev => prev.filter(p => p.id !== selectedPlan.id));

      toast.success(`Plan "${selectedPlan.name}" deleted`);
      setDeleteDialogOpen(false);
    } catch (error) {
      console.error("Failed to delete plan:", error);
      toast.error("Failed to delete plan");
    } finally {
      setIsDeleting(false);
    }
  }, [selectedPlan, searchParams, setSearchParams]);

  // -------------------------------------------------------------------------
  // GAP-W9: Sharing
  // -------------------------------------------------------------------------

  const handleOpenShare = useCallback(async () => {
    if (!currentWorkflowId) return;
    setShowShareDialog(true);
    setShareError(null);
    try {
      const result = await workflowsApi.getWorkflowShares(currentWorkflowId);
      setCurrentShares(result.shares || []);
    } catch (err) {
      console.error("Failed to load shares:", err);
      setCurrentShares([]);
    }
  }, [currentWorkflowId]);

  const handleShare = useCallback(async () => {
    if (!currentWorkflowId || !shareEmail.trim()) return;
    setShareError(null);
    try {
      await workflowsApi.shareWorkflow(currentWorkflowId, shareEmail.trim(), sharePermission);
      setShareEmail('');
      const result = await workflowsApi.getWorkflowShares(currentWorkflowId);
      setCurrentShares(result.shares || []);
      toast.success("Workflow shared");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to share";
      setShareError(msg);
    }
  }, [currentWorkflowId, shareEmail, sharePermission]);

  const handleUnshare = useCallback(async (userId: string) => {
    if (!currentWorkflowId) return;
    try {
      await workflowsApi.unshareWorkflow(currentWorkflowId, userId);
      setCurrentShares(prev => prev.filter(s => s.user_id !== userId));
      toast.success("Share removed");
    } catch (err) {
      console.error("Failed to remove share:", err);
      toast.error("Failed to remove share");
    }
  }, [currentWorkflowId]);

  // -------------------------------------------------------------------------
  // Clipboard / Copy-Paste
  // -------------------------------------------------------------------------

  const handleCopyNodes = useCallback((ids: string[]) => {
    const nodesToCopy = nodes.filter((n) => ids.includes(n.id));
    if (nodesToCopy.length === 0) return;
    setClipboard({ nodes: nodesToCopy });
    toast.success(`${nodesToCopy.length} node${nodesToCopy.length > 1 ? 's' : ''} copied`);
  }, [nodes]);

  const handlePasteNodes = useCallback((position: { x: number; y: number }) => {
    if (!clipboard || clipboard.nodes.length === 0) return;

    const offset = { x: 50, y: 50 };
    const newNodes = clipboard.nodes.map((node, index) => ({
      ...node,
      id: `node-${Date.now()}-${index}`,
      position: {
        x: position.x + (node.position.x - clipboard.nodes[0].position.x) + offset.x,
        y: position.y + (node.position.y - clipboard.nodes[0].position.y) + offset.y,
      },
      status: "idle" as const,
      outputs: undefined,
    }));

    const updatedNodes = [...nodes, ...newNodes];
    setNodes(updatedNodes);
    pushHistory(updatedNodes, connections);
    setSelectedNodeIds(newNodes.map((n) => n.id));
    toast.success(`${newNodes.length} node${newNodes.length > 1 ? 's' : ''} pasted`);
  }, [clipboard, nodes, connections, pushHistory]);

  const handleDuplicateNodes = useCallback((ids: string[]) => {
    const nodesToDuplicate = nodes.filter((n) => ids.includes(n.id));
    if (nodesToDuplicate.length === 0) return;

    const offset = { x: 50, y: 50 };
    const newNodes = nodesToDuplicate.map((node, index) => ({
      ...node,
      id: `node-${Date.now()}-${index}`,
      position: {
        x: node.position.x + offset.x,
        y: node.position.y + offset.y,
      },
      status: "idle" as const,
      outputs: undefined,
    }));

    const updatedNodes = [...nodes, ...newNodes];
    setNodes(updatedNodes);
    pushHistory(updatedNodes, connections);
    setSelectedNodeIds(newNodes.map((n) => n.id));
    toast.success(`${newNodes.length} node${newNodes.length > 1 ? 's' : ''} duplicated`);
  }, [nodes, connections, pushHistory]);

  const handleSelectAll = useCallback(() => {
    setSelectedNodeIds(nodes.map((n) => n.id));
  }, [nodes]);

  const handleOpenNodeProperties = useCallback((id: string) => {
    setSelectedNodeIds([id]);
  }, []);

  // -------------------------------------------------------------------------
  // Execution: SSE event handler + trigger
  // -------------------------------------------------------------------------

  const handleExecutionEvent = useCallback((event: ExecutionEvent) => {
    const timestamp = event.timestamp || new Date().toISOString();
    const eventWithTimestamp = { ...event, timestamp };
    setExecutionEvents(prev => {
      const updated = [...prev.slice(-499), eventWithTimestamp];
      try {
        const minimal = updated.slice(-100).map(e => ({
          type: e.type,
          timestamp: e.timestamp,
          node_id: e.node_id,
          message: e.message,
          error: e.error,
          duration_ms: e.duration_ms,
        }));
        ssSet(WF_STORAGE.executionEvents, JSON.stringify(minimal));
      } catch { /* ignore quota errors */ }
      return updated;
    });

    switch (event.type) {
      case 'start':
      case 'workflow_start':
        setExecutionId(event.execution_id);
        toast.info(`Workflow started${event.execution_id ? ` (ID: ${event.execution_id})` : ''}`);
        break;
      case 'node_start':
        setNodes(prev => prev.map(node =>
          node.id === event.node_id
            ? { ...node, status: "running" as const }
            : node
        ));
        setRunningNodeId(event.node_id);
        break;
      case 'node_complete':
        setNodes(prev => prev.map(node =>
          node.id === event.node_id
            ? {
                ...node,
                status: "success" as const,
                outputs: event.output
                  ? (typeof event.output === 'string'
                      ? [event.output]
                      : [JSON.stringify(event.output, null, 2)])
                  : ["Completed successfully"]
              }
            : node
        ));
        break;
      case 'node_error':
        setNodes(prev => prev.map(node =>
          node.id === event.node_id
            ? {
                ...node,
                status: "error" as const,
                outputs: event.error ? [event.error] : ["Execution failed"],
              }
            : node
        ));
        break;
      case 'checkpoint':
        toast.info(`Checkpoint reached: ${event.checkpoint_id || 'unknown'}`);
        break;
      case 'error':
        setWorkflowStatus("error");
        toast.error(event.error || event.message || "Workflow execution failed");
        break;
      case 'complete':
      case 'workflow_complete':
        setWorkflowStatus("success");
        setWorkflowResult(event.result);
        toast.success(`Workflow completed${event.duration_ms ? ` in ${event.duration_ms}ms` : ''}`);
        break;
      case 'approval_pending':
        // Update node status to awaiting_approval and inject approval_request_id into config
        setNodes(prev => prev.map(node =>
          node.id === event.node_id
            ? {
                ...node,
                status: "awaiting_approval" as const,
                config: {
                  ...(node.config || {}),
                  approval_request_id: event.approval_request_id,
                },
              }
            : node
        ));
        // Store pending approval for toast notification via WorkflowCanvas
        setPendingApproval({
          approval_request_id: event.approval_request_id,
          workflow_id: event.workflow_id,
          workflow_name: event.workflow_name,
          node_id: event.node_id,
          prompt: event.prompt,
        });
        break;
      case 'approval_resolved':
        // Clear approval_request_id from node config and reset status to running
        setNodes(prev => prev.map(node =>
          node.id === event.node_id
            ? {
                ...node,
                status: "running" as const,
                config: {
                  ...(node.config || {}),
                  approval_request_id: undefined,
                },
              }
            : node
        ));
        break;
    }
  }, []);

  const triggerScenarioSSE = useCallback(async (
    scenarioName: string,
    payload: Record<string, unknown>,
  ): Promise<Error | null> => {
    const MAX_SSE_RETRIES = 3;
    const SSE_BASE_DELAY = 1000;
    const HEARTBEAT_TIMEOUT = 30000;

    let lastError: Error | null = null;
    for (let attempt = 0; attempt <= MAX_SSE_RETRIES; attempt++) {
      try {
        if (attempt > 0) {
          const delay = SSE_BASE_DELAY * Math.pow(2, attempt - 1);
          console.warn(`SSE connection lost, retrying in ${delay}ms (attempt ${attempt})`);
          await new Promise(r => setTimeout(r, delay));
        }

        const controller = new AbortController();
        let heartbeatTimer: ReturnType<typeof setTimeout> | null = null;

        const resetHeartbeat = () => {
          if (heartbeatTimer) clearTimeout(heartbeatTimer);
          heartbeatTimer = setTimeout(() => {
            console.warn("SSE heartbeat timeout -- aborting connection");
            controller.abort();
          }, HEARTBEAT_TIMEOUT);
        };

        resetHeartbeat();

        try {
          await fetchStream(
            `/workflow-scenarios/${scenarioName}/trigger`,
            {
              method: 'POST',
              body: JSON.stringify(payload),
            },
            (data) => {
              resetHeartbeat();
              try {
                const event = JSON.parse(data);
                if (event.type === 'heartbeat') return;
                handleExecutionEvent(event);
              } catch (e) {
                console.error("Failed to parse SSE event:", e);
              }
            },
            controller.signal,
          );
        } finally {
          if (heartbeatTimer) clearTimeout(heartbeatTimer);
        }

        lastError = null;
        break;
      } catch (error) {
        lastError = error instanceof Error ? error : new Error(String(error));
        if (attempt >= MAX_SSE_RETRIES) break;
      }
    }
    return lastError;
  }, [handleExecutionEvent]);

  // -------------------------------------------------------------------------
  // Run / Stop / Reset
  // -------------------------------------------------------------------------

  const handleRunWorkflow = useCallback(async () => {
    const planId = searchParams.get('planId');

    if (!planId && !selectedWorkflow) {
      toast.error("No workflow to run");
      return;
    }

    // Plan execution path
    if (planId && !selectedWorkflow) {
      setWorkflowResult(null);
      setExecutionEvents([]);
      ssRemove(WF_STORAGE.executionEvents);

      // Pre-execution validation
      try {
        const validation = await plansApi.validatePlan(Number(planId));
        if (!validation.valid) {
          setWorkflowStatus("idle");
          setBackendPlanStatus(null);
          const errorSummary = validation.errors.join("; ");
          toast.error(`Validation failed: ${errorSummary}`, { duration: 8000 });
          for (const issue of validation.node_issues || []) {
            toast.warning(`${issue.node_id} (${issue.agent}): ${issue.issues.join(", ")}`, { duration: 6000 });
          }
          return;
        }
        for (const warning of validation.warnings || []) {
          toast.warning(warning, { duration: 5000 });
        }
      } catch (validationError) {
        console.warn("Pre-execution validation failed:", validationError);
      }

      setIsRunning(true);
      setWorkflowStatus("running");
      setBackendPlanStatus("executing");

      try {
        const result = await plansApi.executePlan(Number(planId));
        setExecutionId(result.execution_id);

        handleExecutionEvent({
          type: 'workflow_start',
          execution_id: result.execution_id,
          message: `Plan execution started`,
          timestamp: new Date().toISOString(),
        });

        let lastNodeCount = 0;
        const startedNodes = new Set<string>();

        const pollExecution = async (): Promise<boolean> => {
          try {
            const executions = await plansApi.getResults(Number(planId));
            const current = executions.find(e => e.id === result.execution_id);
            if (!current) return false;

            const nodeResults = current.node_results || [];
            if (nodeResults.length > lastNodeCount) {
              for (let i = lastNodeCount; i < nodeResults.length; i++) {
                const nr = nodeResults[i];
                if (!startedNodes.has(nr.node_id)) {
                  startedNodes.add(nr.node_id);
                  handleExecutionEvent({
                    type: 'node_start',
                    node_id: nr.node_id,
                    message: `${nr.agent || nr.node_id}: started`,
                    timestamp: new Date().toISOString(),
                  });
                }
                const eventType = nr.status === 'failed' ? 'node_error' : 'node_complete';
                handleExecutionEvent({
                  type: eventType,
                  node_id: nr.node_id,
                  message: nr.status === 'failed'
                    ? `${nr.agent || nr.node_id}: ${nr.error || 'Failed'}`
                    : `${nr.agent || nr.node_id}: completed`,
                  error: nr.error,
                  output: nr.output,
                  duration_ms: nr.duration_ms,
                  timestamp: new Date().toISOString(),
                });
              }
              lastNodeCount = nodeResults.length;
            }

            if (current.status === "completed") {
              setIsRunning(false);
              setWorkflowStatus("success");
              setBackendPlanStatus("completed");
              setWorkflowResult(current.node_results);
              handleExecutionEvent({
                type: 'workflow_complete',
                message: 'Plan completed',
                duration_ms: current.duration_ms,
                timestamp: new Date().toISOString(),
              });
              return true;
            } else if (current.status === "failed" || current.status === "cancelled") {
              setIsRunning(false);
              setWorkflowStatus("error");
              setBackendPlanStatus(current.status);
              setWorkflowResult(current.node_results);
              handleExecutionEvent({
                type: 'error',
                message: `Plan execution ${current.status}`,
                duration_ms: current.duration_ms,
                timestamp: new Date().toISOString(),
              });
              toast.error(`Plan execution ${current.status}`);
              return true;
            }
          } catch (pollError) {
            console.error("Error polling execution status:", pollError);
          }
          return false;
        };

        const firstDone = await new Promise<boolean>(resolve =>
          setTimeout(async () => resolve(await pollExecution()), 500)
        );

        if (!firstDone) {
          const pollInterval = setInterval(async () => {
            const done = await pollExecution();
            if (done) clearInterval(pollInterval);
          }, 2000);

          setTimeout(() => {
            clearInterval(pollInterval);
            if (isRunningRef.current) {
              toast.warning(
                "Execution is still running but status polling has timed out after 5 minutes. Check the run history for results.",
                { duration: 10000 }
              );
              setWorkflowStatus("idle");
              setIsRunning(false);
            }
          }, 300000);
        }
      } catch (error) {
        setIsRunning(false);
        setWorkflowStatus("error");
        toast.error(error instanceof Error ? error.message : "Failed to execute plan");
      }
      return;
    }

    // Scenario execution path
    const hasRequiredInputs = scenarioInputs.some(i => i.required);
    if (hasRequiredInputs && Object.keys(pendingInputs).length === 0) {
      setInputModalOpen(true);
      return;
    }

    setInputModalOpen(false);
    setIsRunning(true);
    setWorkflowStatus("running");
    setCurrentStep(0);
    setWorkflowResult(null);
    setExecutionId(null);
    setExecutionEvents([]);

    setNodes(prev => prev.map(node => ({
      ...node,
      status: "idle" as const,
      outputs: undefined
    })));

    if (validateOnRun) {
      toast.info("Validating workflow...");
      await new Promise(resolve => setTimeout(resolve, 300));
    }

    if (selectedWorkflow) {
      try {
        const validation = await scenariosApi.validateInputs(selectedWorkflow.name, pendingInputs);
        if (validation?.errors?.length) {
          toast.error(`Validation errors: ${validation.errors.join(', ')}`);
          setIsRunning(false);
          return;
        }
      } catch {
        console.warn('Input validation skipped: endpoint not available');
      }
    }

    const triggerPayload = {
      ...pendingInputs,
      ...(sourceTemplateId ? { _template_id: sourceTemplateId } : {}),
      ...(sourceTemplateVersionId ? { _template_version_id: sourceTemplateVersionId } : {}),
    };

    const lastError = await triggerScenarioSSE(selectedWorkflow!.name, triggerPayload);

    if (lastError) {
      console.error("Workflow execution failed:", lastError);
      setWorkflowStatus("error");
      toast.error(lastError.message || "Execution failed");
    }
    setIsRunning(false);
    setRunningNodeId(null);
    setPendingInputs({});
  }, [selectedWorkflow, validateOnRun, triggerScenarioSSE, scenarioInputs, pendingInputs, sourceTemplateId, sourceTemplateVersionId, searchParams, handleExecutionEvent]);

  const handleInputSubmit = useCallback((values: Record<string, unknown>, files: Record<string, File>) => {
    setPendingInputs(values);
    setInputModalOpen(false);
    setTimeout(() => {
      const runWithInputs = async () => {
        if (!selectedWorkflow) return;

        setIsRunning(true);
        setWorkflowStatus("running");
        setCurrentStep(0);
        setWorkflowResult(null);
        setExecutionId(null);
        setExecutionEvents([]);

        setNodes(prev => prev.map(node => ({
          ...node,
          status: "idle" as const,
          outputs: undefined
        })));

        if (validateOnRun) {
          toast.info("Validating workflow...");
          await new Promise(resolve => setTimeout(resolve, 300));
        }

        try {
          const filePaths: Record<string, string> = {};
          if (Object.keys(files).length > 0) {
            toast.info("Uploading files...");
            for (const [inputName, file] of Object.entries(files)) {
              try {
                const result = await scenariosApi.uploadWorkflowFile(file, inputName);
                filePaths[inputName] = result.path;
              } catch (error) {
                console.error(`Failed to upload file ${inputName}:`, error);
                toast.error(`Failed to upload ${file.name}`);
                throw error;
              }
            }
          }

          const allInputs = {
            ...values,
            ...filePaths,
            ...(sourceTemplateId ? { _template_id: sourceTemplateId } : {}),
            ...(sourceTemplateVersionId ? { _template_version_id: sourceTemplateVersionId } : {}),
          };

          const sseError = await triggerScenarioSSE(selectedWorkflow.name, allInputs);
          if (sseError) {
            throw sseError;
          }
        } catch (error) {
          console.error("Workflow execution failed:", error);
          setWorkflowStatus("error");
          toast.error(error instanceof Error ? error.message : "Execution failed");
        } finally {
          setIsRunning(false);
          setRunningNodeId(null);
          setPendingInputs({});
        }
      };
      runWithInputs();
    }, 0);
  }, [selectedWorkflow, validateOnRun, triggerScenarioSSE, sourceTemplateId, sourceTemplateVersionId]);

  const handleRunNode = useCallback(async (id: string) => {
    toast.info("Single node execution runs the full workflow");
    handleRunWorkflow();
  }, [handleRunWorkflow]);

  const handleStopWorkflow = useCallback(async () => {
    const planId = searchParams.get('planId');

    setIsRunning(false);
    setRunningNodeId(null);
    setWorkflowStatus("idle");
    setCurrentStep(0);
    setNodes((prev) =>
      prev.map((node) =>
        node.status === "running" ? { ...node, status: "idle" as const } : node
      )
    );

    if (planId) {
      try {
        await plansApi.cancelPlan(Number(planId));
      } catch {
        try {
          await plansApi.resetStuckPlan(Number(planId));
        } catch {
          // Already completed or non-executing state
        }
      }
    }

    toast.info("Workflow stopped");
  }, [searchParams]);

  // -------------------------------------------------------------------------
  // Save handlers
  // -------------------------------------------------------------------------

  const handleSaveCustomWorkflow = useCallback(async () => {
    if (!currentWorkflowId) return;
    try {
      await workflowsApi.updateWorkflow(currentWorkflowId, {
        workflow_json: {
          nodes: nodes.map((n) => ({
            id: n.id,
            type: (n.type as 'start' | 'task' | 'router' | 'tool' | 'end') || 'task',
            label: n.label,
            description: n.description,
            agent: n.agent,
            task: n.task,
            tool: n.tool,
            arguments: n.arguments,
            position: n.position,
          })),
          edges: connections.map((c) => ({
            id: c.id,
            source: c.from,
            target: c.to,
          })),
        },
      });
      setIsDirty(false);
      toast.success('Workflow saved');
    } catch (err) {
      console.error('Failed to save workflow:', err);
      toast.error('Failed to save workflow');
    }
  }, [currentWorkflowId, nodes, connections]);

  const handleSave = useCallback(async () => {
    if (currentWorkflowId) {
      await handleSaveCustomWorkflow();
      return;
    }

    const planId = searchParams.get('planId');

    if (planId) {
      try {
        await plansApi.updatePlan(Number(planId), {
          nodes: nodes.map((n) => ({
            id: n.id,
            type: n.type,
            label: n.label,
            agent: n.agent,
            task: n.task || n.description,
            description: n.description || n.task,
            tool: n.tool,
            arguments: n.arguments,
            depends_on: connections
              .filter((c) => c.to === n.id)
              .map((c) => c.from),
          })),
          edges: connections.map((c, idx) => ({
            id: c.id || `edge-${idx}`,
            from: c.from,
            to: c.to,
          })),
        });
        setIsDirty(false);
        toast.success("Plan saved");
      } catch (error) {
        console.error("Failed to save plan:", error);
        toast.error("Failed to save plan");
      }
      return;
    }

    if (isAIGenerated && nodes.length > 0) {
      try {
        const saved = await plansApi.createPlan({
          name: `AI Workflow ${new Date().toLocaleDateString()}`,
          description: "Saved from workflow editor",
          conversation_id: crypto.randomUUID(),
          nodes: nodes.map((n) => ({
            id: n.id,
            agent: n.agent || n.label,
            task: n.task || n.description || n.label,
            depends_on: connections
              .filter((c) => c.to === n.id)
              .map((c) => c.from),
          })),
          edges: connections.map((c, idx) => ({
            id: c.id || `edge-${idx}`,
            from: c.from,
            to: c.to,
          })),
          ai_generated: true,
        });
        setSearchParams({ planId: String(saved.id) }, { replace: true });
        setIsDirty(false);
        toast.success("Plan created and saved");
      } catch (error) {
        console.error("Failed to create plan:", error);
        toast.error("Failed to save as new plan");
      }
      return;
    }

    if (selectedWorkflow) {
      toast.info("Scenarios are read-only. Use 'Save as Template' to create a copy.");
    } else {
      toast.info("No changes to save. Create a workflow first.");
    }
  }, [nodes, connections, searchParams, setSearchParams, isAIGenerated, selectedWorkflow, currentWorkflowId, handleSaveCustomWorkflow]);

  const handleSaveAsTemplate = useCallback(() => {
    window.dispatchEvent(
      new CustomEvent('dryade:host:command', {
        detail: {
          plugin: 'templates',
          command: 'openSaveDialog',
        },
      })
    );
  }, []);

  const handleResetWorkflow = useCallback(() => {
    setNodes((prev) =>
      prev.map((node) => ({ ...node, status: "idle" as const, outputs: undefined }))
    );
    setWorkflowStatus("idle");
    setCurrentStep(0);
    toast.info("Workflow reset");
  }, []);

  const handleResetStuckPlan = useCallback(async () => {
    const planId = searchParams.get('planId');
    if (!planId) return;
    try {
      await plansApi.resetStuckPlan(Number(planId));
      setBackendPlanStatus("failed");
      setIsRunning(false);
      setWorkflowStatus("idle");
      toast.success("Plan reset - you can now re-run or edit it");
    } catch (error) {
      toast.error("Failed to reset plan");
      console.error(error);
    }
  }, [searchParams]);

  // -------------------------------------------------------------------------
  // Plan loaded callback (from planner sidebar)
  // -------------------------------------------------------------------------

  const handlePlanLoaded = useCallback((planId: number, planNodes: WorkflowNode[], planEdges: { from: string; to: string }[]) => {
    const loadedConns: Connection[] = planEdges.map((e, i) => ({
      id: `edge-${i}`,
      from: e.from,
      to: e.to,
    }));

    const { allNodes, allEdges } = injectStartEndNodes(planNodes, loadedConns);

    setNodes(allNodes);
    setConnections(allEdges);
    setHistory([{ nodes: allNodes, connections: allEdges }]);
    setHistoryIndex(0);
    setIsAIGenerated(true);
    setSelectedWorkflowId(null);
    setSelectedWorkflow(null);
    setIsDirty(false);
    initialLoadComplete.current = false;

    setSearchParams({ planId: String(planId) }, { replace: true });
    sessionStorage.setItem('lastPlanId', String(planId));
  }, [setSearchParams]);

  // Track dirty state
  useEffect(() => {
    if (!initialLoadComplete.current) {
      initialLoadComplete.current = true;
      return;
    }
    setIsDirty(true);
  }, [nodes, connections]);

  // -------------------------------------------------------------------------
  // Custom workflow CRUD (GAP-W6 / W8)
  // -------------------------------------------------------------------------

  const loadWorkflowById = useCallback(async (workflowId: number) => {
    try {
      const workflow = await workflowsApi.getWorkflow(workflowId);
      const wfJson = workflow.workflow_json;

      if (wfJson?.nodes) {
        const loadedNodes: WorkflowNode[] = wfJson.nodes.map((n) => ({
          id: n.id,
          type: (n.type as WorkflowNodeType) || 'task',
          label: n.label || 'Node',
          description: n.description,
          agent: n.agent,
          task: n.task,
          position: n.position || { x: 100, y: 100 },
          status: 'idle' as const,
        }));
        setNodes(loadedNodes);

        const loadedConns: Connection[] = (wfJson.edges || []).map((e) => ({
          id: e.id,
          from: e.source,
          to: e.target,
        }));
        setConnections(loadedConns);
        setHistory([{ nodes: loadedNodes, connections: loadedConns }]);
        setHistoryIndex(0);
      }

      setCurrentWorkflowId(workflowId);
      setSelectedWorkflowId(null);
      setSelectedWorkflow(null);
      setSelectedPlan(null);
      setIsAIGenerated(false);
      setWorkflowStatus('idle');
      setIsDirty(false);
      initialLoadComplete.current = false;

      const params = new URLSearchParams(window.location.search);
      params.set('workflowId', String(workflowId));
      params.delete('planId');
      window.history.replaceState({}, '', `?${params}`);

      toast.success(`Loaded workflow: ${workflow.name}`);
    } catch (err) {
      console.error('Failed to load workflow:', err);
      toast.error('Failed to load workflow');
    }
  }, []);

  // Auto-load workflowId from URL on mount
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const wfId = params.get('workflowId');
    if (wfId) {
      loadWorkflowById(parseInt(wfId, 10));
    }
  }, [loadWorkflowById]);

  const handleCreateWorkflowSubmit = useCallback(async () => {
    if (!newWorkflowName.trim()) return;
    setIsCreating(true);
    try {
      const defaultWorkflowJson = {
        nodes: [
          { id: 'start-node', type: 'start' as const, label: 'Start', position: { x: 400, y: 50 } },
          { id: 'end-node', type: 'end' as const, label: 'End', position: { x: 400, y: 350 } },
        ],
        edges: [
          { id: 'start-to-end', source: 'start-node', target: 'end-node' },
        ],
      };
      const workflow = await createWorkflowMutation.mutateAsync({
        name: newWorkflowName.trim(),
        description: newWorkflowDescription.trim() || undefined,
        workflow_json: defaultWorkflowJson,
      });

      const canvasNodes: WorkflowNode[] = defaultWorkflowJson.nodes.map((n) => ({
        id: n.id,
        type: n.type as WorkflowNodeType,
        label: n.label,
        position: n.position,
        status: 'idle' as const,
      }));
      const canvasConns: Connection[] = defaultWorkflowJson.edges.map((e) => ({
        id: e.id,
        from: e.source,
        to: e.target,
      }));

      setNodes(canvasNodes);
      setConnections(canvasConns);
      setHistory([{ nodes: canvasNodes, connections: canvasConns }]);
      setHistoryIndex(0);
      setCurrentWorkflowId(workflow.id);
      setSelectedWorkflowId(null);
      setSelectedWorkflow(null);
      setSelectedPlan(null);
      setIsAIGenerated(false);
      setWorkflowStatus('idle');
      setIsDirty(false);
      initialLoadComplete.current = false;

      setShowCreateDialog(false);
      setNewWorkflowName('');
      setNewWorkflowDescription('');

      const params = new URLSearchParams(window.location.search);
      params.set('workflowId', String(workflow.id));
      params.delete('planId');
      window.history.replaceState({}, '', `?${params}`);

      toast.success(`Created workflow: ${workflow.name}`);
    } catch (err) {
      console.error('Failed to create workflow:', err);
      toast.error('Failed to create workflow');
    } finally {
      setIsCreating(false);
    }
  }, [newWorkflowName, newWorkflowDescription, createWorkflowMutation]);

  const handleDeleteCustomWorkflow = useCallback(async (workflowId: number) => {
    try {
      await deleteWorkflowMutation.mutateAsync(workflowId);
      if (currentWorkflowId === workflowId) {
        setCurrentWorkflowId(null);
        setNodes(defaultNodes);
        setConnections(defaultConnections);
        setHistory([{ nodes: defaultNodes, connections: defaultConnections }]);
        setHistoryIndex(0);
        const params = new URLSearchParams(window.location.search);
        params.delete('workflowId');
        window.history.replaceState({}, '', params.toString() ? `?${params}` : window.location.pathname);
      }
      toast.success('Workflow deleted');
    } catch (err) {
      console.error('Failed to delete workflow:', err);
      toast.error('Failed to delete workflow');
    }
  }, [currentWorkflowId, deleteWorkflowMutation]);

  const handlePublishCustomWorkflow = useCallback(async () => {
    if (!currentWorkflowId) return;

    const errors: string[] = [];

    if (nodes.length === 0) {
      errors.push('Workflow must have at least one node');
    }

    if (nodes.length > 1) {
      const connectedNodeIds = new Set<string>();
      connections.forEach(c => {
        connectedNodeIds.add(c.from);
        connectedNodeIds.add(c.to);
      });
      const disconnected = nodes.filter(n => !connectedNodeIds.has(n.id));
      if (disconnected.length > 0) {
        errors.push(`Disconnected nodes: ${disconnected.map(n => n.label || n.id).join(', ')}`);
      }
    }

    const noAgent = nodes.filter(n => n.type === 'task' && !n.agent);
    if (noAgent.length > 0) {
      errors.push(`Nodes missing agent assignment: ${noAgent.map(n => n.label || n.id).join(', ')}`);
    }

    if (errors.length > 0) {
      errors.forEach(e => toast.error(e));
      return;
    }

    try {
      await publishWorkflowMutation.mutateAsync(currentWorkflowId);
      toast.success('Workflow published');
    } catch (err) {
      console.error('Failed to publish workflow:', err);
      toast.error('Failed to publish workflow');
    }
  }, [currentWorkflowId, publishWorkflowMutation, nodes, connections]);

  const handleArchiveCustomWorkflow = useCallback(async () => {
    if (!currentWorkflowId) return;
    try {
      await archiveWorkflowMutation.mutateAsync(currentWorkflowId);
      setCurrentWorkflowId(null);
      setNodes(defaultNodes);
      setConnections(defaultConnections);
      setHistory([{ nodes: defaultNodes, connections: defaultConnections }]);
      setHistoryIndex(0);
      const params = new URLSearchParams(window.location.search);
      params.delete('workflowId');
      window.history.replaceState({}, '', params.toString() ? `?${params}` : window.location.pathname);
      toast.success('Workflow archived');
    } catch (err) {
      console.error('Failed to archive workflow:', err);
      toast.error('Failed to archive workflow');
    }
  }, [currentWorkflowId, archiveWorkflowMutation]);

  // -------------------------------------------------------------------------
  // Template plugin message listener
  // -------------------------------------------------------------------------

  useEffect(() => {
    const handlePluginMessage = (event: CustomEvent) => {
      const { plugin, type, payload } = event.detail || {};
      if (plugin !== 'templates') return;

      try {
        switch (type) {
          case 'loadTemplate': {
            const { nodes: templateNodes, edges: templateEdges, templateName, templateId, templateVersionId } = payload || {};
            if (!templateNodes || !Array.isArray(templateNodes)) {
              console.error('Invalid template payload: missing or invalid nodes array');
              toast.error('Failed to load template: invalid data');
              return;
            }
            if (!templateEdges || !Array.isArray(templateEdges)) {
              console.error('Invalid template payload: missing or invalid edges array');
              toast.error('Failed to load template: invalid data');
              return;
            }

            setSourceTemplateId(templateId ?? null);
            setSourceTemplateVersionId(templateVersionId ?? null);

            const convertedNodes: WorkflowNode[] = templateNodes.map((n: Record<string, unknown>) => ({
              id: n.id,
              type: (n.type as WorkflowNodeType) || 'task',
              label: n.label || 'Node',
              description: n.description,
              agent: n.agent,
              task: n.task,
              position: n.position || { x: 100, y: 100 },
              status: 'idle' as const,
            }));
            const convertedConnections: Connection[] = templateEdges.map((e: Record<string, unknown>) => ({
              id: e.id,
              from: e.from || e.source,
              to: e.to || e.target,
            }));

            setNodes(convertedNodes);
            setConnections(convertedConnections);
            setHistory([{ nodes: convertedNodes, connections: convertedConnections }]);
            setHistoryIndex(0);
            setIsDirty(false);
            initialLoadComplete.current = false;

            toast.success(`Loaded template: ${templateName || 'Template'}`);
            break;
          }

          case 'requestWorkflow': {
            const responseTimeout = setTimeout(() => {
              console.warn('requestWorkflow response timeout (5s)');
              toast.error('Template save timed out');
            }, 5000);

            try {
              window.dispatchEvent(
                new CustomEvent('dryade:host:response', {
                  detail: {
                    type: 'workflowData',
                    payload: {
                      nodes: nodes.map(n => ({
                        id: n.id,
                        type: n.type,
                        label: n.label,
                        description: n.description,
                        agent: n.agent,
                        task: n.task,
                        position: n.position,
                      })),
                      edges: connections.map(c => ({
                        id: c.id,
                        from: c.from,
                        to: c.to,
                      })),
                    },
                  },
                })
              );
              clearTimeout(responseTimeout);
            } catch (dispatchErr) {
              clearTimeout(responseTimeout);
              console.error('Failed to dispatch workflow data:', dispatchErr);
              toast.error('Failed to send workflow data to template plugin');
            }
            break;
          }
        }
      } catch (err) {
        console.error('Bridge communication error:', err);
        toast.error('Failed to process template data');
      }
    };

    window.addEventListener('dryade:plugin:message', handlePluginMessage as EventListener);
    return () => {
      window.removeEventListener('dryade:plugin:message', handlePluginMessage as EventListener);
    };
  }, [nodes, connections]);

  // -------------------------------------------------------------------------
  // Keyboard shortcuts
  // -------------------------------------------------------------------------

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const isMac = navigator.platform.toUpperCase().indexOf("MAC") >= 0;
      const cmdKey = isMac ? e.metaKey : e.ctrlKey;
      const target = e.target as HTMLElement;
      const isInputField = target.tagName === "INPUT" || target.tagName === "TEXTAREA";

      if (cmdKey && e.key === "Enter" && !isRunning) {
        e.preventDefault();
        handleRunWorkflow();
      }

      if (e.key === "Escape") {
        e.preventDefault();
        if (isRunning) {
          handleStopWorkflow();
        } else {
          setSelectedNodeIds([]);
        }
      }

      if (cmdKey && e.key === "s") {
        e.preventDefault();
        handleSave();
      }

      if (cmdKey && e.key === "z" && !e.shiftKey) {
        e.preventDefault();
        handleUndo();
      }

      if (cmdKey && e.key === "z" && e.shiftKey) {
        e.preventDefault();
        handleRedo();
      }

      if (cmdKey && e.key === "a" && !isInputField) {
        e.preventDefault();
        handleSelectAll();
      }

      if (cmdKey && e.key === "c" && !isInputField && selectedNodeIds.length > 0) {
        e.preventDefault();
        handleCopyNodes(selectedNodeIds);
      }

      if (cmdKey && e.key === "v" && !isInputField && clipboard) {
        e.preventDefault();
        handlePasteNodes({ x: 400, y: 300 });
      }

      if (cmdKey && e.key === "d" && !isInputField && selectedNodeIds.length > 0) {
        e.preventDefault();
        handleDuplicateNodes(selectedNodeIds);
      }

      if ((e.key === "Delete" || e.key === "Backspace") && !isInputField && selectedNodeIds.length > 0) {
        e.preventDefault();
        selectedNodeIds.forEach((id) => handleDeleteNode(id));
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [
    isRunning,
    selectedNodeIds,
    clipboard,
    handleRunWorkflow,
    handleStopWorkflow,
    handleSave,
    handleDeleteNode,
    handleUndo,
    handleRedo,
    handleSelectAll,
    handleCopyNodes,
    handlePasteNodes,
    handleDuplicateNodes,
  ]);

  // -------------------------------------------------------------------------
  // Return everything WorkflowPage needs
  // -------------------------------------------------------------------------

  return {
    searchParams,
    setSearchParams,

    workflows,
    userPlans,
    workflowsLoading,
    selectedWorkflowId,
    selectedWorkflow,
    selectedPlan,
    isAIGenerated,

    nodes,
    connections,
    selectedNodeIds,
    setSelectedNodeIds,
    selectedNode,
    runningNodeId,
    isRunning,
    workflowStatus,
    currentStep,
    totalSteps,
    validateOnRun,
    setValidateOnRun,
    sidebarWidth,
    setSidebarWidth,
    sidebarCollapsed,
    setSidebarCollapsed,
    executionId,
    workflowResult,

    inputModalOpen,
    setInputModalOpen,
    scenarioInputs,

    backendPlanStatus,

    resultModalOpen,
    setResultModalOpen,

    executionEvents,
    logCollapsed,
    setLogCollapsed,

    clipboard,

    canUndo,
    canRedo,

    sourceTemplateId,
    setSourceTemplateId,
    sourceTemplateVersionId,
    setSourceTemplateVersionId,

    isDirty,
    setIsDirty,
    initialLoadComplete,

    deleteDialogOpen,
    setDeleteDialogOpen,
    isDeleting,

    showCreateDialog,
    setShowCreateDialog,
    newWorkflowName,
    setNewWorkflowName,
    newWorkflowDescription,
    setNewWorkflowDescription,
    isCreating,

    currentWorkflowId,

    myWorkflows,
    loadingMyWorkflows,
    refetchWorkflows,
    publishWorkflowMutation,
    archiveWorkflowMutation,
    deleteWorkflowMutation,

    showShareDialog,
    setShowShareDialog,
    shareEmail,
    setShareEmail,
    sharePermission,
    setSharePermission,
    currentShares,
    shareError,

    handleUndo,
    handleRedo,
    handleSelectWorkflow,
    handleSelectPlan,
    handleCreateWorkflow,
    handleAddNode,
    handleUpdateNode,
    handleNodesChange,
    handleConnectionsChange,
    handleDeleteNode,
    handleDeleteWorkflow,
    handleOpenShare,
    handleShare,
    handleUnshare,
    handleCopyNodes,
    handlePasteNodes,
    handleDuplicateNodes,
    handleSelectAll,
    handleOpenNodeProperties,
    handleRunWorkflow,
    handleInputSubmit,
    handleRunNode,
    handleStopWorkflow,
    handleSave,
    handleSaveAsTemplate,
    handleResetWorkflow,
    handleResetStuckPlan,
    handlePlanLoaded,
    loadWorkflowById,
    handleCreateWorkflowSubmit,
    handleDeleteCustomWorkflow,
    handlePublishCustomWorkflow,
    handleArchiveCustomWorkflow,

    pendingApproval,
    clearPendingApproval,
  };
}
