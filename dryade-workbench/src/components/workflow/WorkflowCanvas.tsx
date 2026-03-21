// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useCallback, useMemo, useEffect, useState, useRef } from "react";
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  useReactFlow,
  BackgroundVariant,
  ConnectionMode,
  MarkerType,
  SelectionMode,
  type OnConnect,
  type NodeTypes,
  type Connection,
  type Edge,
  type Node,
  type OnNodesChange,
  type OnEdgesChange,
  type Viewport,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { layoutGraph } from "@/utils/layoutGraph";
import { type WorkflowNode, type Connection as WorkflowConnection, type NodeType } from "@/types/workflow";
import FlowNode, { type FlowNodeData, type FlowNodeType } from "./FlowNode";
import { ApprovalNode } from "./ApprovalNode";
import WorkflowToolbar from "./WorkflowToolbar";
import CanvasContextMenu from "./CanvasContextMenu";
import NodeContextMenu from "./NodeContextMenu";

interface WorkflowCanvasProps {
  nodes: WorkflowNode[];
  connections: WorkflowConnection[];
  onNodesChange: (nodes: WorkflowNode[]) => void;
  onConnectionsChange?: (connections: WorkflowConnection[]) => void;
  onNodeSelect: (ids: string[]) => void;
  selectedNodeIds: string[];
  runningNodeId: string | null;
  onRunNode: (id: string) => void;
  onDeleteNode: (id: string) => void;
  onDuplicateNodes: (ids: string[]) => void;
  onCopyNodes: (ids: string[]) => void;
  onPasteNodes: (position: { x: number; y: number }) => void;
  hasClipboard: boolean;
  onOpenNodeProperties: (id: string) => void;
  onSaveAsTemplate?: () => void;
  pendingApproval?: {
    approval_request_id: number;
    workflow_id: number;
    workflow_name: string;
    node_id: string;
    prompt: string;
  } | null;
  onClearPendingApproval?: () => void;
  highlightNodeId?: string | null;
}

// Define node types
const nodeTypes: NodeTypes = {
  custom: FlowNode,
  approval: ApprovalNode,
};

// Node handlers interface for context menu
interface NodeHandlers {
  onRunNode: (id: string) => void;
  onDuplicateNode: (id: string) => void;
  onCopyNode: (id: string) => void;
  onDeleteNode: (id: string) => void;
  onOpenProperties: (id: string) => void;
  onViewOutputs?: (id: string) => void;
}

// Convert WorkflowNode to React Flow Node
const toFlowNode = (
  node: WorkflowNode,
  handlers: NodeHandlers,
): FlowNodeType => ({
  id: node.id,
  // Approval nodes use their own dedicated component; all others use FlowNode ("custom")
  type: node.type === "approval" ? "approval" : "custom",
  position: node.position,
  data: {
    label: node.label,
    nodeType: node.type,
    description: node.description,
    status: node.status,
    outputs: node.outputs,
    onRunNode: handlers.onRunNode,
    onDuplicateNode: handlers.onDuplicateNode,
    onCopyNode: handlers.onCopyNode,
    onDeleteNode: handlers.onDeleteNode,
    onOpenProperties: handlers.onOpenProperties,
    onViewOutputs: handlers.onViewOutputs,
  },
});

// Convert WorkflowConnection to React Flow Edge
const toFlowEdge = (connection: WorkflowConnection, runningNodeId: string | null): Edge => {
  const isActive = connection.from === runningNodeId || connection.to === runningNodeId;
  
  return {
    id: connection.id,
    source: connection.from,
    target: connection.to,
    type: "smoothstep",
    animated: isActive,
    style: {
      stroke: isActive 
        ? "hsl(var(--primary))" 
        : "hsl(var(--primary) / 0.6)",
      strokeWidth: isActive ? 2.5 : 1.5,
      filter: isActive ? "drop-shadow(0 0 6px hsl(var(--primary) / 0.5))" : undefined,
    },
    markerEnd: {
      type: MarkerType.ArrowClosed,
      width: 16,
      height: 16,
      color: isActive 
        ? "hsl(var(--primary))" 
        : "hsl(var(--primary) / 0.6)",
    },
  };
};

// Canvas background — dot grid
const canvasBg = { color: "hsl(var(--muted-foreground) / 0.25)", variant: BackgroundVariant.Dots, size: 1.5 };

// Inner component that uses useReactFlow
const WorkflowCanvasInner = ({
  nodes: workflowNodes,
  connections: workflowConnections,
  onNodesChange: onWorkflowNodesChange,
  onConnectionsChange,
  onNodeSelect,
  selectedNodeIds,
  runningNodeId,
  onRunNode,
  onDeleteNode,
  onDuplicateNodes,
  onCopyNodes,
  onPasteNodes,
  hasClipboard,
  onOpenNodeProperties,
  onSaveAsTemplate,
  pendingApproval,
  onClearPendingApproval,
}: WorkflowCanvasProps) => {
  const navigate = useNavigate();
  const { fitView, zoomIn, zoomOut, setViewport, getViewport, screenToFlowPosition } = useReactFlow();
  const [snapToGrid, setSnapToGrid] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [contextMenuOpen, setContextMenuOpen] = useState(false);
  const [contextMenuPosition, setContextMenuPosition] = useState({ x: 0, y: 0 });
  const [flowPosition, setFlowPosition] = useState({ x: 0, y: 0 });
  const canvasRef = useRef<HTMLDivElement>(null);
  // Track last shown approval toast to avoid duplicates
  const lastApprovalIdRef = useRef<number | null>(null);

  // Approval pending toast — fires once per unique approval_request_id
  useEffect(() => {
    if (!pendingApproval) return;
    if (lastApprovalIdRef.current === pendingApproval.approval_request_id) return;
    lastApprovalIdRef.current = pendingApproval.approval_request_id;

    toast.warning(
      `Approval required: ${pendingApproval.prompt.slice(0, 80)}${pendingApproval.prompt.length > 80 ? '...' : ''}`,
      {
        duration: 10000,
        action: {
          label: "Review",
          onClick: () => {
            navigate(
              `/workspace/workflows?workflowId=${pendingApproval.workflow_id}&highlight=${pendingApproval.node_id}`
            );
          },
        },
      }
    );
    // Clear pending approval after toast fires
    onClearPendingApproval?.();
  }, [pendingApproval, navigate, onClearPendingApproval]);

  // Single-node wrappers for context menu handlers
  const handleDuplicateSingleNode = useCallback((id: string) => {
    onDuplicateNodes([id]);
  }, [onDuplicateNodes]);

  const handleCopySingleNode = useCallback((id: string) => {
    onCopyNodes([id]);
  }, [onCopyNodes]);

  // Node handlers for context menu
  const nodeHandlers: NodeHandlers = useMemo(() => ({
    onRunNode,
    onDuplicateNode: handleDuplicateSingleNode,
    onCopyNode: handleCopySingleNode,
    onDeleteNode,
    onOpenProperties: onOpenNodeProperties,
  }), [onRunNode, handleDuplicateSingleNode, handleCopySingleNode, onDeleteNode, onOpenNodeProperties]);

  // Convert to React Flow format
  const flowNodes = useMemo(
    () => workflowNodes.map((n) => toFlowNode(n, nodeHandlers)),
    [workflowNodes, nodeHandlers]
  );

  const flowEdges = useMemo(
    () => workflowConnections.map((c) => toFlowEdge(c, runningNodeId)),
    [workflowConnections, runningNodeId]
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(flowNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(flowEdges);

  // Sync nodes from parent when they change
  useEffect(() => {
    setNodes(flowNodes);
  }, [flowNodes, setNodes]);

  // Sync edges from parent when they change
  useEffect(() => {
    setEdges(flowEdges);
  }, [flowEdges, setEdges]);

  // Handle new connections
  const onConnect: OnConnect = useCallback(
    (connection: Connection) => {
      const newEdge: Edge = {
        id: `edge-${Date.now()}`,
        source: connection.source!,
        target: connection.target!,
        sourceHandle: connection.sourceHandle ?? undefined,
        targetHandle: connection.targetHandle ?? undefined,
        type: "smoothstep",
        animated: false,
        style: { stroke: "hsl(var(--primary) / 0.6)", strokeWidth: 1.5 },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 16,
          height: 16,
          color: "hsl(var(--primary) / 0.6)",
        },
      };
      setEdges((eds) => addEdge(newEdge, eds));
      
      // Sync back to parent
      if (onConnectionsChange) {
        const newConnection: WorkflowConnection = {
          id: newEdge.id,
          from: connection.source!,
          to: connection.target!,
        };
        onConnectionsChange([...workflowConnections, newConnection]);
      }
    },
    [setEdges, onConnectionsChange, workflowConnections]
  );

  // Handle node position changes
  const handleNodesChange: OnNodesChange<FlowNodeType> = useCallback(
    (changes) => {
      onNodesChange(changes);
      
      // Sync position changes back to parent
      const positionChanges = changes.filter(
        (change): change is typeof change & { id: string; position: { x: number; y: number } } => 
          change.type === "position" && "position" in change && change.position !== undefined
      );
      
      if (positionChanges.length > 0) {
        const updatedNodes = workflowNodes.map((node) => {
          const change = positionChanges.find((c) => c.id === node.id);
          if (change) {
            const position = snapToGrid
              ? { x: Math.round(change.position.x / 20) * 20, y: Math.round(change.position.y / 20) * 20 }
              : change.position;
            return { ...node, position };
          }
          return node;
        });
        onWorkflowNodesChange(updatedNodes);
      }
    },
    [onNodesChange, workflowNodes, onWorkflowNodesChange, snapToGrid]
  );

  // Handle node selection (multi-select)
  const handleSelectionChange = useCallback(
    ({ nodes: selectedNodes }: { nodes: Node[] }) => {
      const ids = selectedNodes.map((n) => n.id);
      onNodeSelect(ids);
    },
    [onNodeSelect]
  );

  // Handle edge deletion
  const handleEdgesChange: OnEdgesChange = useCallback(
    (changes) => {
      onEdgesChange(changes);
      
      // Sync deletions back to parent
      const removals = changes.filter((change) => change.type === "remove");
      if (removals.length > 0 && onConnectionsChange) {
        const removedIds = removals.map((r) => r.id);
        const updatedConnections = workflowConnections.filter(
          (c) => !removedIds.includes(c.id)
        );
        onConnectionsChange(updatedConnections);
      }
    },
    [onEdgesChange, workflowConnections, onConnectionsChange]
  );

  // Handle dropping new nodes from palette
  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  }, []);

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();

      const nodeType = event.dataTransfer.getData("nodeType") as NodeType | "";
      if (!nodeType) return;

      const reactFlowBounds = event.currentTarget.getBoundingClientRect();
      const position = {
        x: event.clientX - reactFlowBounds.left,
        y: event.clientY - reactFlowBounds.top,
      };

      const newNode: WorkflowNode = {
        id: `node-${Date.now()}`,
        type: nodeType,
        label: `New ${nodeType.charAt(0).toUpperCase() + nodeType.slice(1)}`,
        position,
        status: "idle",
      };

      onWorkflowNodesChange([...workflowNodes, newNode]);
    },
    [workflowNodes, onWorkflowNodesChange]
  );

  // Track viewport changes for zoom display
  const handleMoveEnd = useCallback((_: unknown, viewport: Viewport) => {
    setZoom(viewport.zoom);
  }, []);

  // Toolbar handlers
  const handleZoomIn = useCallback(() => zoomIn(), [zoomIn]);
  const handleZoomOut = useCallback(() => zoomOut(), [zoomOut]);
  const handleFitView = useCallback(() => fitView({ padding: 0.2 }), [fitView]);
  const handleResetZoom = useCallback(() => {
    const viewport = getViewport();
    setViewport({ ...viewport, zoom: 1 });
    setZoom(1);
  }, [getViewport, setViewport]);
  const handleToggleSnap = useCallback(() => setSnapToGrid((prev) => !prev), []);

  const handleAutoLayout = useCallback(() => {
    const positions = layoutGraph(
      workflowNodes.map(n => n.id),
      workflowConnections,
      { direction: 'horizontal', nodeWidth: 220, nodeHeight: 120, hSpacing: 100, vSpacing: 60, startX: 100, startY: 80 },
    );

    // Apply positions to nodes
    const layoutedNodes = workflowNodes.map((node) => ({
      ...node,
      position: positions.get(node.id) || node.position,
    }));

    // Map workflow nodes back to ReactFlow format for direct state update
    const layoutedFlowNodes = layoutedNodes.map((node) =>
      toFlowNode(node, nodeHandlers)
    );

    // Use setNodes directly to avoid parent state round-trip race condition.
    // ReactFlow 12.5.0+ processes this synchronously before the next paint,
    // so fitView can see the new positions immediately (no setTimeout needed).
    setNodes(layoutedFlowNodes);
    fitView({ padding: 0.2 });

    // Persist layout to parent for save/reload (does not affect fitView timing)
    onWorkflowNodesChange(layoutedNodes);
  }, [workflowNodes, workflowConnections, onWorkflowNodesChange, fitView, nodeHandlers, setNodes]);

  // Keep a stable ref to the latest handleAutoLayout so the mount effect
  // doesn't re-run (and cancel its timer) every time the callback identity changes.
  const autoLayoutRef = useRef(handleAutoLayout);
  useEffect(() => { autoLayoutRef.current = handleAutoLayout; }, [handleAutoLayout]);

  // Auto-layout on first load when nodes exist.
  // Uses a 250ms delay so ReactFlow has time to mount and measure node dimensions.
  const hasAutoLayoutRun = useRef(false);
  useEffect(() => {
    if (!hasAutoLayoutRun.current && workflowNodes.length > 0) {
      hasAutoLayoutRun.current = true;
      const timer = setTimeout(() => {
        autoLayoutRef.current();
      }, 250);
      return () => clearTimeout(timer);
    }
  }, [workflowNodes.length]);

  const handleAlignNodes = useCallback(
    (alignment: "left" | "center" | "right" | "top" | "middle" | "bottom") => {
      if (selectedNodeIds.length < 2) return;
      
      const selectedNodes = workflowNodes.filter((n) => selectedNodeIds.includes(n.id));
      let targetValue: number;

      switch (alignment) {
        case "left":
          targetValue = Math.min(...selectedNodes.map((n) => n.position.x));
          break;
        case "center": {
          const minX = Math.min(...selectedNodes.map((n) => n.position.x));
          const maxX = Math.max(...selectedNodes.map((n) => n.position.x));
          targetValue = (minX + maxX) / 2;
          break;
        }
        case "right":
          targetValue = Math.max(...selectedNodes.map((n) => n.position.x));
          break;
        case "top":
          targetValue = Math.min(...selectedNodes.map((n) => n.position.y));
          break;
        case "middle": {
          const minY = Math.min(...selectedNodes.map((n) => n.position.y));
          const maxY = Math.max(...selectedNodes.map((n) => n.position.y));
          targetValue = (minY + maxY) / 2;
          break;
        }
        case "bottom":
          targetValue = Math.max(...selectedNodes.map((n) => n.position.y));
          break;
      }

      const alignedNodes = workflowNodes.map((node) => {
        if (!selectedNodeIds.includes(node.id)) return node;
        
        const isHorizontal = ["left", "center", "right"].includes(alignment);
        return {
          ...node,
          position: isHorizontal
            ? { ...node.position, x: targetValue }
            : { ...node.position, y: targetValue },
        };
      });

      onWorkflowNodesChange(alignedNodes);
    },
    [selectedNodeIds, workflowNodes, onWorkflowNodesChange]
  );

  const handleDeleteSelected = useCallback(() => {
    selectedNodeIds.forEach((id) => onDeleteNode(id));
  }, [selectedNodeIds, onDeleteNode]);

  const handleDuplicateSelected = useCallback(() => {
    onDuplicateNodes(selectedNodeIds);
  }, [selectedNodeIds, onDuplicateNodes]);

  // Context menu handlers
  const handleAddNodeAtPosition = useCallback(
    (type: NodeType, position: { x: number; y: number }, agentName?: string) => {
      // For agent nodes, use the agent name if provided
      const label = agentName
        ? agentName
        : `New ${type.charAt(0).toUpperCase() + type.slice(1)}`;

      const newNode: WorkflowNode = {
        id: `node-${Date.now()}`,
        type,
        label,
        position,
        status: "idle",
        // Store agent reference for agent nodes
        ...(type === "agent" && agentName ? { agent: agentName } : {}),
      };
      onWorkflowNodesChange([...workflowNodes, newNode]);
    },
    [workflowNodes, onWorkflowNodesChange]
  );

  const handleContextMenu = useCallback((event: React.MouseEvent) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    setContextMenuPosition({
      x: event.clientX - bounds.left,
      y: event.clientY - bounds.top,
    });
  }, []);

  const handleSelectAll = useCallback(() => {
    onNodeSelect(workflowNodes.map((n) => n.id));
  }, [workflowNodes, onNodeSelect]);

  // Handle pane context menu (right-click on canvas background)
  const handlePaneContextMenu = useCallback(
    (event: React.MouseEvent) => {
      event.preventDefault();
      // Screen position for menu placement
      setContextMenuPosition({
        x: event.clientX,
        y: event.clientY,
      });
      // Flow position for adding nodes
      const flowPos = screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });
      setFlowPosition(flowPos);
      setContextMenuOpen(true);
    },
    [screenToFlowPosition]
  );

  // Wrapper to use flowPosition for adding nodes from context menu
  const handleAddNodeFromContextMenu = useCallback(
    (type: NodeType, agentName?: string) => {
      handleAddNodeAtPosition(type, flowPosition, agentName);
    },
    [handleAddNodeAtPosition, flowPosition]
  );

  // Wrapper to use flowPosition for pasting nodes
  const handlePasteFromContextMenu = useCallback(() => {
    onPasteNodes(flowPosition);
  }, [onPasteNodes, flowPosition]);

  return (
    <div className="w-full h-full rounded-xl border border-border overflow-hidden relative" ref={canvasRef}>
      {/* Canvas Context Menu - controlled dropdown positioned at mouse */}
      <CanvasContextMenu
        open={contextMenuOpen}
        onOpenChange={setContextMenuOpen}
        hasClipboard={hasClipboard}
        position={contextMenuPosition}
        snapToGrid={snapToGrid}
        onAddNode={handleAddNodeFromContextMenu}
        onPaste={handlePasteFromContextMenu}
        onSelectAll={handleSelectAll}
        onFitView={handleFitView}
        onResetZoom={handleResetZoom}
        onToggleGrid={handleToggleSnap}
        onSaveAsTemplate={onSaveAsTemplate}
      />

      <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={handleNodesChange}
          onEdgesChange={handleEdgesChange}
          onConnect={onConnect}
          onSelectionChange={handleSelectionChange}
          onDragOver={onDragOver}
          onDrop={onDrop}
          onMoveEnd={handleMoveEnd}
          onPaneContextMenu={handlePaneContextMenu}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          connectionMode={ConnectionMode.Loose}
          selectionMode={SelectionMode.Partial}
          selectionOnDrag
          panOnDrag={[1, 2]}
          selectNodesOnDrag={false}
          snapToGrid={snapToGrid}
          snapGrid={[20, 20]}
          className="!bg-transparent"
          defaultEdgeOptions={{
            type: "smoothstep",
            style: { stroke: "hsl(var(--primary) / 0.6)", strokeWidth: 1.5 },
            markerEnd: {
              type: MarkerType.ArrowClosed,
              width: 16,
              height: 16,
              color: "hsl(var(--primary) / 0.6)",
            },
          }}
          connectionLineStyle={{
            stroke: "hsl(var(--primary))",
            strokeWidth: 2,
            strokeDasharray: "5 5",
          }}
          proOptions={{ hideAttribution: true }}
        >
          <Background
            variant={canvasBg.variant}
            gap={20}
            size={canvasBg.size}
            color={canvasBg.color}
          />
          <MiniMap
            nodeColor={(node) => {
              const nodeData = node.data as FlowNodeData | undefined;
              switch (nodeData?.status) {
                case "running":
                  return "hsl(var(--primary))";
                case "success":
                  return "hsl(var(--success))";
                case "error":
                  return "hsl(var(--destructive))";
                default:
                  return "hsl(var(--muted-foreground) / 0.5)";
              }
            }}
            maskColor="hsl(var(--background) / 0.8)"
            pannable
            zoomable
          />
        </ReactFlow>

      {/* Toolbar */}
      <WorkflowToolbar
        zoom={zoom}
        snapToGrid={snapToGrid}
        selectedCount={selectedNodeIds.length}
        onZoomIn={handleZoomIn}
        onZoomOut={handleZoomOut}
        onFitView={handleFitView}
        onResetZoom={handleResetZoom}
        onToggleSnap={handleToggleSnap}
        onAutoLayout={handleAutoLayout}
        onAlignNodes={handleAlignNodes}
        onDeleteSelected={handleDeleteSelected}
        onDuplicateSelected={handleDuplicateSelected}
      />
      
      {/* Empty State */}
      {workflowNodes.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="text-center max-w-sm p-6">
            <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto mb-4">
              <svg
                width="32"
                height="32"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="text-primary"
              >
                <rect x="3" y="3" width="7" height="7" rx="1" />
                <rect x="14" y="3" width="7" height="7" rx="1" />
                <rect x="3" y="14" width="7" height="7" rx="1" />
                <path d="M14 17h7" />
                <path d="M17.5 14v7" />
              </svg>
            </div>
            <h3 className="text-lg font-semibold text-foreground mb-2">
              Build your workflow
            </h3>
            <p className="text-sm text-muted-foreground mb-4">
              Drag agents from the right panel or right-click to add nodes.
              Connect nodes by dragging from one handle to another.
            </p>
            <div className="flex items-center justify-center gap-4 text-xs text-muted-foreground">
              <span className="flex items-center gap-1.5">
                <kbd className="px-1.5 py-0.5 rounded bg-muted font-mono">Right-click</kbd>
                to add
              </span>
              <span className="flex items-center gap-1.5">
                <kbd className="px-1.5 py-0.5 rounded bg-muted font-mono">Drag</kbd>
                handles
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// Wrapper component with provider
const WorkflowCanvas = (props: WorkflowCanvasProps) => {
  return (
    <ReactFlowProvider>
      <WorkflowCanvasInner {...props} />
    </ReactFlowProvider>
  );
};

export default WorkflowCanvas;
