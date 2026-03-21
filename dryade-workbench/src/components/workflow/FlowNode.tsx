// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { memo, useCallback, useMemo, useState } from "react";
import { Handle, Position, type NodeProps, type Node } from "@xyflow/react";
import { cn } from "@/lib/utils";
import { type NodeStatus, type NodeType } from "@/types/workflow";
import { getNodeConfig } from "@/config/nodeConfig";
import {
  Play,
  Copy,
  Check,
  Loader2,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  XCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import NodeContextMenu from "./NodeContextMenu";

export interface FlowNodeData extends Record<string, unknown> {
  label: string;
  nodeType: NodeType;
  description?: string;
  status: NodeStatus;
  outputs?: string[];
  onRunNode?: (id: string) => void;
  onDuplicateNode?: (id: string) => void;
  onCopyNode?: (id: string) => void;
  onDeleteNode?: (id: string) => void;
  onOpenProperties?: (id: string) => void;
  onViewOutputs?: (id: string) => void;
}

export type FlowNodeType = Node<FlowNodeData, "custom">;

const statusLabels: Record<NodeStatus, string> = {
  idle: "Ready",
  pending: "Pending",
  running: "Running",
  success: "Complete",
  complete: "Complete",
  error: "Failed",
  skipped: "Skipped",
  awaiting_approval: "Needs Review",
};

// HSL accent colors per node type — primary #baf0b6 = hsl(117, 68%, 83%)
// All node types use #baf0b6 mint as base glow, with hue shifts for differentiation
const nodeTypeAccent: Record<NodeType, string> = {
  input:    "117, 68%, 83%",   // #baf0b6 — primary mint
  task:     "117, 50%, 75%",   // muted mint
  output:   "90, 60%, 78%",    // warm lime shift
  decision: "140, 55%, 78%",   // cool teal shift
  agent:    "117, 68%, 83%",   // #baf0b6 — primary mint
  tool:     "150, 55%, 78%",   // cyan-mint
  start:    "117, 68%, 83%",   // #baf0b6 — primary mint
  router:   "95, 60%, 78%",    // yellow-mint shift
  end:      "130, 50%, 75%",   // forest-mint shift
  approval: "38, 92%, 70%",    // amber — #fbbf24 hue for human approval
};

// Status-driven glow intensity — #baf0b6 is light so needs strong opacity to pop on dark canvas
const statusGlowIntensity: Record<NodeStatus, { inner: number; outer: number }> = {
  idle:               { inner: 0,     outer: 0 },
  pending:            { inner: 0.3,   outer: 0.2 },
  running:            { inner: 0.5,   outer: 0.55 },
  success:            { inner: 0.4,   outer: 0.45 },
  complete:           { inner: 0.4,   outer: 0.45 },
  error:              { inner: 0.45,  outer: 0.5 },
  skipped:            { inner: 0.15,  outer: 0.1 },
  awaiting_approval:  { inner: 0.55,  outer: 0.6 },  // strong amber pulse
};

// Override accent hue for status states — running/success stay mint, error shifts warm
const statusAccentOverride: Partial<Record<NodeStatus, string>> = {
  running:            "117, 68%, 83%",   // #baf0b6 primary mint — bright pulse
  success:            "117, 60%, 78%",   // mint-success
  complete:           "117, 60%, 78%",
  error:              "0, 72%, 70%",     // light red (stays visible on dark)
  awaiting_approval:  "38, 92%, 70%",   // amber override for approval waiting
};

const StatusIcon = ({ status }: { status: NodeStatus }) => {
  switch (status) {
    case "running":
      return <Loader2 size={12} className="animate-spin text-primary" />;
    case "success":
      return <CheckCircle2 size={12} className="text-success" />;
    case "error":
      return <XCircle size={12} className="text-destructive" />;
    default:
      return null;
  }
};

const FlowNode = ({ id, data, selected }: NodeProps<FlowNodeType>) => {
  const config = getNodeConfig(data.nodeType);
  const Icon = config.icon;
  const [isExpanded, setIsExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  const isRunning = data.status === "running";
  const hasOutput = data.outputs && data.outputs.length > 0;
  const outputPreview = hasOutput ? data.outputs!.join("\n").slice(0, 80) : "";

  // Resolve accent color — status overrides node type for running/error/success
  const accentHSL = statusAccentOverride[data.status] ?? nodeTypeAccent[data.nodeType] ?? nodeTypeAccent.task;
  const glow = statusGlowIntensity[data.status] ?? statusGlowIntensity.idle;

  // Single branded node style — green-accent radial glow + status-driven outer glow
  const nodeStyle = useMemo(() => {
    const glowShadow = `0 0 36px -2px hsla(${accentHSL}, ${glow.outer}), 0 0 72px -6px hsla(${accentHSL}, ${glow.outer * 0.5})`;
    const baseShadow = `0 2px 12px -2px hsla(0, 0%, 0%, 0.4)`;

    // Radial accent glow layered on top of the tinted card background
    const radialGlow = `radial-gradient(ellipse 160% 120% at 8% 12%, hsla(${accentHSL}, ${glow.inner}) 0%, hsla(${accentHSL}, 0.06) 60%, transparent 100%)`;
    // Dark mint card surface — boosted opacity for clear card visibility against canvas
    const cardBg = `linear-gradient(135deg, hsla(${accentHSL}, 0.18) 0%, hsla(${accentHSL}, 0.10) 100%)`;

    // Hover glow — always available, applied via CSS variable + shadow transition
    const hoverGlow = `0 0 28px -2px hsla(${accentHSL}, 0.4), 0 0 56px -6px hsla(${accentHSL}, 0.2)`;

    return {
      width: isExpanded ? 280 : 200,
      backgroundImage: `${radialGlow}, ${cardBg}`,
      backgroundColor: `hsl(var(--card))`,
      boxShadow: glow.outer > 0 ? `${baseShadow}, ${glowShadow}` : baseShadow,
      // Left accent border — #baf0b6 colored bar
      borderLeft: `3px solid hsla(${accentHSL}, 0.9)`,
      // CSS variable consumed by hover state
      "--node-hover-shadow": `${baseShadow}, ${hoverGlow}`,
      "--accent-hsl": accentHSL,
    } as React.CSSProperties;
  }, [isExpanded, accentHSL, glow]);

  const handleCopyOutput = useCallback(async () => {
    if (!data.outputs) return;
    try {
      await navigator.clipboard.writeText(data.outputs.join("\n"));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error("Failed to copy:", err);
    }
  }, [data.outputs]);

  const handleRun = useCallback(() => data.onRunNode?.(id), [data.onRunNode, id]);
  const handleDuplicate = useCallback(() => data.onDuplicateNode?.(id), [data.onDuplicateNode, id]);
  const handleCopy = useCallback(() => data.onCopyNode?.(id), [data.onCopyNode, id]);
  const handleDelete = useCallback(() => data.onDeleteNode?.(id), [data.onDeleteNode, id]);
  const handleOpenProperties = useCallback(() => data.onOpenProperties?.(id), [data.onOpenProperties, id]);
  const handleViewOutputs = useCallback(() => data.onViewOutputs?.(id), [data.onViewOutputs, id]);

  return (
    <NodeContextMenu
      nodeId={id}
      isRunning={isRunning}
      hasOutputs={hasOutput}
      onRun={handleRun}
      onDuplicate={handleDuplicate}
      onCopy={handleCopy}
      onDelete={handleDelete}
      onOpenProperties={handleOpenProperties}
      onViewOutputs={handleViewOutputs}
    >
    <div
      className={cn(
        // Base card — rounded corners, transition, hover
        "rounded-xl border flow-node-hover",
        "transition-all duration-200 ease-out",
        // Single branded style — glass-dark base
        "bg-card/90 backdrop-blur-md",
        // Default border: green-accent at 30% opacity
        "border-primary/30",
        // Hover — lift + glow (glow via flow-node-hover CSS class) + stronger border
        "hover:scale-[1.015] hover:brightness-110 hover:border-primary/50",
        // Selected — scale up + strong accent border
        selected && "scale-[1.015] border-primary/80",
        // Running — breathing animation
        isRunning && "animate-pulse-subtle node-running",
        // Completion animation
        (data.status === "success" || data.status === "complete") && "node-complete",
        // Error animation
        (data.status === "error") && "node-error-shake"
      )}
      style={{
        ...nodeStyle,
        padding: "12px 14px",
        borderColor: selected
          ? `hsla(${accentHSL}, 0.8)`
          : `hsla(${accentHSL}, 0.3)`,
        // Selected: accent ring + glow
        ...(selected ? {
          boxShadow: `0 0 0 1.5px hsla(${accentHSL}, 0.4), ${nodeStyle.boxShadow}, 0 0 56px -8px hsla(${accentHSL}, 0.25)`,
        } : {}),
      }}
    >
      {/* Input Handle */}
      <Handle
        type="target"
        position={Position.Left}
        className={cn(
          "!w-3 !h-3 !-left-[6px] !rounded-full",
          "!bg-card !border-2 !border-border/50",
          "hover:!border-primary hover:!bg-primary/20 hover:!scale-125",
          "transition-all duration-150"
        )}
      />

      {/* Header */}
      <div className="flex items-start gap-2.5 mb-2">
        {/* Icon — embedded pill, no border */}
        <div className={cn(
          "p-1.5 rounded-lg shrink-0",
          config.bgClass,
        )}>
          <Icon size={16} className={cn(config.colorClass, "opacity-80")} />
        </div>

        {/* Title & Status */}
        <div className="flex-1 min-w-0 pt-0.5">
          <h4 className="font-semibold text-foreground text-[13px] leading-tight truncate">
            {data.label}
          </h4>
          <div className="flex items-center gap-1.5 mt-1">
            <span className={cn(
              "w-1.5 h-1.5 rounded-full transition-colors",
              data.status === "idle" && "bg-muted-foreground/30",
              data.status === "pending" && "bg-muted-foreground/40",
              data.status === "running" && "bg-primary animate-pulse",
              (data.status === "success" || data.status === "complete") && "bg-success",
              data.status === "error" && "bg-destructive",
              data.status === "skipped" && "bg-muted-foreground/20",
            )} />
            <span className="text-[10px] text-muted-foreground/70 font-medium">
              {statusLabels[data.status]}
            </span>
            <StatusIcon status={data.status} />
          </div>
        </div>

        {/* Run Button */}
        {data.onRunNode && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                className={cn(
                  "h-6 w-6 rounded-md shrink-0",
                  isRunning
                    ? "text-primary bg-primary/10"
                    : "text-muted-foreground/50 hover:text-primary hover:bg-primary/10"
                )}
                onClick={(e) => {
                  e.stopPropagation();
                  if (!isRunning && data.onRunNode) {
                    data.onRunNode(id);
                  }
                }}
                disabled={isRunning}
              >
                {isRunning ? (
                  <Loader2 size={12} className="animate-spin" />
                ) : (
                  <Play size={12} />
                )}
              </Button>
            </TooltipTrigger>
            <TooltipContent side="top" className="text-xs">
              {isRunning ? "Running..." : "Run node"}
            </TooltipContent>
          </Tooltip>
        )}
      </div>

      {/* Description (expanded) */}
      {data.description && isExpanded && (
        <p className="text-xs text-muted-foreground/60 mb-2 leading-relaxed">
          {data.description}
        </p>
      )}

      {/* Output Preview (expanded) */}
      {hasOutput && isExpanded && (
        <div className="mb-2">
          <div className="flex items-center justify-between mb-1">
            <span className="text-[10px] text-muted-foreground/50 uppercase tracking-wider font-medium">
              Output
            </span>
            <Button
              variant="ghost"
              size="icon-sm"
              className="h-5 w-5"
              onClick={(e) => {
                e.stopPropagation();
                handleCopyOutput();
              }}
            >
              {copied ? (
                <Check size={10} className="text-success" />
              ) : (
                <Copy size={10} className="text-muted-foreground/40" />
              )}
            </Button>
          </div>
          <div className="p-2 rounded-md bg-background/60 border border-border/20 text-[10px] font-mono text-muted-foreground/70 leading-relaxed">
            {outputPreview}
            {outputPreview.length < (data.outputs?.join("\n").length || 0) && (
              <span className="text-muted-foreground/30">...</span>
            )}
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between gap-2 pt-1">
        {/* Type Badge — ultra-subtle */}
        <span className="text-[9px] px-1.5 py-0.5 rounded font-mono uppercase tracking-wide text-muted-foreground/40">
          {config.label}
        </span>

        {/* Expand Toggle */}
        {(data.description || hasOutput) && (
          <Button
            variant="ghost"
            size="icon-sm"
            className="h-5 w-5 text-muted-foreground/40 hover:text-foreground"
            onClick={(e) => {
              e.stopPropagation();
              setIsExpanded(!isExpanded);
            }}
          >
            {isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          </Button>
        )}
      </div>

      {/* Output Handle */}
      <Handle
        type="source"
        position={Position.Right}
        className={cn(
          "!w-3 !h-3 !-right-[6px] !rounded-full",
          "!bg-card !border-2 !border-border/50",
          "hover:!border-primary hover:!bg-primary/20 hover:!scale-125",
          "transition-all duration-150"
        )}
      />
    </div>
    </NodeContextMenu>
  );
};

export default memo(FlowNode);
