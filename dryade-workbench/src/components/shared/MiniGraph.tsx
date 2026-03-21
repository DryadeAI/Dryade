// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
/**
 * MiniGraph - Reusable mini workflow graph SVG visualization
 *
 * Uses shared Kahn's topological layout (horizontal direction for compact preview).
 */
import { useMemo } from "react";
import { layoutGraph } from "@/utils/layoutGraph";

export interface MiniGraphNode {
  id: string;
  label: string;
  /** Optional secondary label (e.g., task description) */
  sublabel?: string;
  status?: string;
}

export interface MiniGraphEdge {
  from: string;
  to: string;
}

export interface MiniGraphProps {
  nodes: MiniGraphNode[];
  edges: MiniGraphEdge[];
  /** Height of the SVG in pixels. Default: 180 */
  height?: number;
  /** Additional CSS classes */
  className?: string;
}

/** Calculate positions for MiniGraph (horizontal layout). */
export function calculateNodePositions(
  nodes: MiniGraphNode[],
  edges: MiniGraphEdge[],
  height: number = 180
): Map<string, { x: number; y: number }> {
  if (nodes.length === 0) return new Map();
  const positions = layoutGraph(
    nodes.map(n => n.id),
    edges,
    { direction: 'horizontal', nodeWidth: 120, nodeHeight: 48, hSpacing: 36, vSpacing: 24, startX: 24, startY: 10 },
  );
  // Center vertically within SVG height
  const allY = Array.from(positions.values()).map(p => p.y);
  const minY = Math.min(...allY);
  const maxY = Math.max(...allY) + 48;
  const contentHeight = maxY - minY;
  const yShift = Math.max(0, (height - contentHeight) / 2) - minY;
  if (yShift !== 0) {
    positions.forEach((pos, id) => positions.set(id, { x: pos.x, y: pos.y + yShift }));
  }
  return positions;
}

/**
 * Mini workflow graph SVG component.
 *
 * Renders a compact SVG visualization of a workflow graph with nodes and edges.
 * Uses Kahn's algorithm to position nodes in topological order (left to right).
 */
export function MiniGraph({
  nodes,
  edges,
  height = 180,
  className,
}: MiniGraphProps) {
  const positions = useMemo(
    () => calculateNodePositions(nodes, edges, height),
    [nodes, edges, height]
  );

  // Calculate SVG dimensions (20% larger nodes)
  const nodeWidth = 120;
  const nodeHeight = 48;
  const maxX = Math.max(0, ...Array.from(positions.values()).map((p) => p.x)) + nodeWidth + 24;
  const svgWidth = Math.max(360, maxX);
  const svgHeight = height;

  return (
    <svg
      viewBox={`0 0 ${svgWidth} ${svgHeight}`}
      className={className ?? `w-full h-[${height}px] bg-muted/30 rounded-md`}
      style={{ height: `${height}px` }}
      preserveAspectRatio="xMidYMid meet"
    >
      <defs>
        <marker
          id="arrowhead"
          markerWidth="8"
          markerHeight="6"
          refX="8"
          refY="3"
          orient="auto"
        >
          <polygon
            points="0 0, 8 3, 0 6"
            className="fill-muted-foreground/50"
          />
        </marker>
      </defs>

      {/* Edges */}
      {edges.map((edge, idx) => {
        const fromPos = positions.get(edge.from);
        const toPos = positions.get(edge.to);
        if (!fromPos || !toPos) return null;

        const startX = fromPos.x + nodeWidth;
        const startY = fromPos.y + nodeHeight / 2;
        const endX = toPos.x;
        const endY = toPos.y + nodeHeight / 2;

        // Quadratic bezier curve
        const midX = (startX + endX) / 2;
        const path = `M ${startX} ${startY} Q ${midX} ${startY} ${midX} ${(startY + endY) / 2} Q ${midX} ${endY} ${endX} ${endY}`;

        return (
          <path
            key={`edge-${idx}`}
            d={path}
            fill="none"
            className="stroke-muted-foreground/40"
            strokeWidth="2"
            markerEnd="url(#arrowhead)"
          />
        );
      })}

      {/* Nodes */}
      {nodes.map((node) => {
        const pos = positions.get(node.id);
        if (!pos) return null;

        // Truncate labels for display (handle undefined labels gracefully)
        const label = node.label || 'Task';
        const displayLabel = label.length > 14
          ? label.slice(0, 12) + "..."
          : label;
        const displaySublabel = node.sublabel
          ? node.sublabel.length > 16
            ? node.sublabel.slice(0, 14) + "..."
            : node.sublabel
          : null;

        return (
          <g key={node.id} transform={`translate(${pos.x}, ${pos.y})`}>
            <rect
              width={nodeWidth}
              height={nodeHeight}
              rx="8"
              className="fill-card stroke-border"
              strokeWidth="1"
            />
            <text
              x={nodeWidth / 2}
              y={displaySublabel ? nodeHeight / 2 - 5 : nodeHeight / 2 + 4}
              textAnchor="middle"
              className="fill-foreground text-[11px] font-medium"
            >
              {displayLabel}
            </text>
            {displaySublabel && (
              <text
                x={nodeWidth / 2}
                y={nodeHeight / 2 + 12}
                textAnchor="middle"
                className="fill-muted-foreground text-[9px]"
              >
                {displaySublabel}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

export default MiniGraph;
