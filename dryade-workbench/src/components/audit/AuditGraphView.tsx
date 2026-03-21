// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useMemo, useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { formatDuration } from "@/lib/format";
import {
  ReactFlow,
  Background,
  Controls,
  type Node,
  type Edge,
  Position,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { NodeResult } from "@/types/execution";

interface AuditGraphViewProps {
  nodes: NodeResult[];
  className?: string;
}

const statusColors: Record<string, { border: string; bg: string; text: string }> = {
  completed: { border: "border-success", bg: "bg-success/10", text: "text-success" },
  failed: { border: "border-destructive", bg: "bg-destructive/10", text: "text-destructive" },
  skipped: { border: "border-muted", bg: "bg-muted/30", text: "text-muted-foreground" },
  running: { border: "border-primary", bg: "bg-primary/10", text: "text-primary" },
};

function AuditNodeComponent({ data }: { data: { label: string; status: string; duration_ms?: number } }) {
  const colors = statusColors[data.status] || statusColors.skipped;
  return (
    <div className={cn("px-4 py-3 rounded-lg border-2 bg-card min-w-[160px] text-center", colors.border, colors.bg)}>
      <p className="text-sm font-medium text-foreground">{data.label}</p>
      <p className={cn("text-xs mt-1 capitalize", colors.text)}>{data.status}</p>
      {data.duration_ms !== undefined && (
        <p className="text-[10px] text-muted-foreground mt-0.5">{data.duration_ms}ms</p>
      )}
    </div>
  );
}

const nodeTypes = { auditNode: AuditNodeComponent };

const usePrefersReducedMotion = () => {
  const [reduced, setReduced] = useState(() =>
    typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const handler = (e: MediaQueryListEvent) => setReduced(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);
  return reduced;
};

const AuditGraphView = ({ nodes: nodeResults, className }: AuditGraphViewProps) => {
  const { t } = useTranslation('audit');
  const prefersReducedMotion = usePrefersReducedMotion();

  const { flowNodes, flowEdges } = useMemo(() => {
    if (nodeResults.length === 0) return { flowNodes: [], flowEdges: [] };

    const Y_SPACING = 120;
    const X_CENTER = 250;

    const flowNodes: Node[] = nodeResults.map((node, idx) => ({
      id: node.node_id,
      type: "auditNode",
      position: { x: X_CENTER, y: idx * Y_SPACING },
      data: {
        label: node.node_id,
        status: node.status,
        duration_ms: node.duration_ms,
      },
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
      draggable: false,
      connectable: false,
    }));

    const flowEdges: Edge[] = nodeResults.slice(1).map((node, idx) => ({
      id: `e-${nodeResults[idx].node_id}-${node.node_id}`,
      source: nodeResults[idx].node_id,
      target: node.node_id,
      animated: !prefersReducedMotion,
      style: { stroke: "hsl(var(--primary))", strokeWidth: 2 },
    }));

    return { flowNodes, flowEdges };
  }, [nodeResults, prefersReducedMotion]);

  if (nodeResults.length === 0) {
    return (
      <div className={cn("flex items-center justify-center p-12 text-sm text-muted-foreground", className)}>
        {t('graph.noNodes')}
      </div>
    );
  }

  return (
    <div className={cn("space-y-0", className)}>
      <div className="h-[500px] rounded-lg border border-border" aria-label="Execution flow graph">
        <ReactFlow
          nodes={flowNodes}
          edges={flowEdges}
          nodeTypes={nodeTypes}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          fitView
          fitViewOptions={{ padding: 0.3 }}
          proOptions={{ hideAttribution: true }}
        >
          <Background gap={20} size={1} />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
      {/* Screen-reader accessible summary of nodes */}
      <ol className="sr-only">
        {nodeResults.map((node) => (
          <li key={node.node_id}>
            {node.node_id}: {node.status}
            {node.duration_ms !== undefined ? `, duration ${formatDuration(node.duration_ms)}` : ""}
          </li>
        ))}
      </ol>
    </div>
  );
};

export default AuditGraphView;
