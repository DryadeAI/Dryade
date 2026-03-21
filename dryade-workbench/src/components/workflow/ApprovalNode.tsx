// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// ApprovalNode — ReactFlow custom node for human-in-loop approval steps (Phase 150)
// Amber color scheme signals "needs human action"

import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { cn } from "@/lib/utils";
import { ShieldCheck } from "lucide-react";

interface ApprovalNodeData extends Record<string, unknown> {
  label?: string;
  prompt?: string;
  approver?: string;
  display_fields?: string[];
  timeout_seconds?: number;
  timeout_action?: string;
  // Runtime fields
  status?: string;
  runtime_status?: string;
  approval_request_id?: number;
}

const ApprovalNode = memo(({ data, selected }: NodeProps) => {
  const nodeData = data as ApprovalNodeData;
  const label = nodeData.label || "Approval";
  const prompt = nodeData.prompt || "";
  const isAwaiting =
    nodeData.status === "awaiting_approval" ||
    nodeData.runtime_status === "awaiting_approval";

  return (
    <div
      className={cn(
        "relative min-w-[140px] max-w-[200px] rounded-lg border-2 px-3 py-2",
        "bg-amber-950/80 backdrop-blur-sm",
        "border-amber-500/70",
        selected
          ? "border-amber-400 ring-2 ring-amber-400/40"
          : "border-amber-500/70",
        isAwaiting && "border-amber-400 ring-2 ring-amber-400/60 animate-pulse"
      )}
      style={{
        boxShadow: isAwaiting
          ? "0 0 12px rgba(245, 158, 11, 0.5), 0 0 24px rgba(245, 158, 11, 0.2)"
          : "0 0 8px rgba(245, 158, 11, 0.2)",
      }}
    >
      {/* Input handle — top */}
      <Handle
        type="target"
        position={Position.Top}
        className="w-3 h-3 !border-amber-400 !bg-amber-950"
      />

      {/* Node header */}
      <div className="flex items-center gap-2 mb-1">
        <div className="flex items-center justify-center w-6 h-6 rounded bg-amber-500/20 shrink-0">
          <ShieldCheck size={14} className="text-amber-400" />
        </div>
        <span className="text-xs font-semibold text-amber-200 truncate flex-1">
          {label}
        </span>
      </div>

      {/* Prompt preview */}
      {prompt && (
        <p className="text-[10px] text-amber-300/70 line-clamp-2 mb-1">{prompt}</p>
      )}

      {/* Awaiting approval badge */}
      {isAwaiting && (
        <div className="flex items-center gap-1 mt-1 px-1.5 py-0.5 rounded-full bg-amber-500/20 border border-amber-400/40 w-fit">
          <div className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-ping" />
          <span className="text-[9px] font-medium text-amber-300">Needs Review</span>
        </div>
      )}

      {/* Approved source handle — right (green) */}
      <Handle
        type="source"
        position={Position.Right}
        id="approved"
        className="w-3 h-3 !border-green-400 !bg-green-700"
        style={{ right: -6, top: "40%" }}
      />

      {/* Rejected source handle — bottom (red) */}
      <Handle
        type="source"
        position={Position.Bottom}
        id="rejected"
        className="w-3 h-3 !border-red-400 !bg-red-900"
      />
    </div>
  );
});

ApprovalNode.displayName = "ApprovalNode";

export default ApprovalNode;
export { ApprovalNode };
export type { ApprovalNodeData };
