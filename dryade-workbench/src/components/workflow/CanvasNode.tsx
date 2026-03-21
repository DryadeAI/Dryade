// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useRef, useCallback, useEffect } from "react";
import { cn } from "@/lib/utils";
import { type WorkflowNode, type NodeStatus } from "@/types/workflow";
import { getNodeConfig, statusColors } from "@/config/nodeConfig";
import {
  MoreHorizontal,
  Play,
  Copy,
  Check,
  Maximize2,
  Minimize2,
  Lock,
  Unlock,
  AlertCircle,
  Loader2,
  GripHorizontal,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";

interface CanvasNodeProps {
  node: WorkflowNode;
  isSelected: boolean;
  onSelect: (id: string) => void;
  onDragStart: (e: React.DragEvent, id: string) => void;
  onRunNode?: (id: string) => void;
  onMoveNode?: (id: string, deltaX: number, deltaY: number) => void;
  schemaLoading?: boolean;
  schemaError?: string | null;
}

// Clear status labels
const statusLabels: Record<NodeStatus, string> = {
  idle: "Pending",
  pending: "Pending",
  running: "Running",
  success: "Success",
  complete: "Complete",
  error: "Failed",
  skipped: "Skipped",
};

const statusBadgeColors: Record<NodeStatus, string> = {
  idle: "bg-muted text-muted-foreground",
  pending: "bg-muted text-muted-foreground",
  running: "bg-primary/20 text-primary",
  success: "bg-success/20 text-success",
  complete: "bg-success/20 text-success",
  error: "bg-destructive/20 text-destructive",
  skipped: "bg-muted text-muted-foreground",
};

const MIN_WIDTH = 180;
const MAX_WIDTH = 400;
const DEFAULT_WIDTH = 220;

const CanvasNode = ({
  node,
  isSelected,
  onSelect,
  onDragStart,
  onRunNode,
  onMoveNode,
  schemaLoading = false,
  schemaError = null,
}: CanvasNodeProps) => {
  const config = getNodeConfig(node.type);
  const Icon = config.icon;

  const [width, setWidth] = useState(DEFAULT_WIDTH);
  const [isCompact, setIsCompact] = useState(true);
  const [isResizing, setIsResizing] = useState(false);
  const [copied, setCopied] = useState(false);
  const [outputDialogOpen, setOutputDialogOpen] = useState(false);
  const [scrollLock, setScrollLock] = useState(true);
  
  const nodeRef = useRef<HTMLDivElement>(null);
  const outputRef = useRef<HTMLDivElement>(null);

  const hasOutput = node.outputs && node.outputs.length > 0;
  const outputPreview = hasOutput ? node.outputs!.join("\n").slice(0, 100) : "";
  const fullOutput = hasOutput ? node.outputs!.join("\n") : "";
  const isOutputTruncated = fullOutput.length > 100;

  // Auto-scroll output when streaming
  useEffect(() => {
    if (scrollLock && outputRef.current && node.status === "running") {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [node.outputs, scrollLock, node.status]);

  // Resize handling
  const handleResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsResizing(true);
  }, []);

  useEffect(() => {
    if (!isResizing) return;

    const handleMouseMove = (e: MouseEvent) => {
      if (!nodeRef.current) return;
      const rect = nodeRef.current.getBoundingClientRect();
      const newWidth = e.clientX - rect.left + 8;
      setWidth(Math.min(Math.max(newWidth, MIN_WIDTH), MAX_WIDTH));
    };

    const handleMouseUp = () => {
      setIsResizing(false);
    };

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    document.body.style.cursor = "ew-resize";
    document.body.style.userSelect = "none";

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, [isResizing]);

  // Copy output
  const handleCopyOutput = useCallback(async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error("Failed to copy:", err);
    }
  }, []);

  const isRunning = node.status === "running";
  const canRun = !isRunning && onRunNode;

  return (
    <>
      <div
        ref={nodeRef}
        className={cn(
          "workflow-node animate-node-appear relative",
          config.borderClass,
          config.bgClass,
          isSelected && "selected ring-2 ring-primary/50",
          isResizing && "cursor-ew-resize"
        )}
        style={{
          position: "absolute",
          left: node.position.x,
          top: node.position.y,
          transform: "translate(-50%, -50%)",
          width: isCompact ? DEFAULT_WIDTH : width,
          minWidth: MIN_WIDTH,
          maxWidth: MAX_WIDTH,
        }}
        onClick={() => onSelect(node.id)}
        draggable={!isResizing}
        onDragStart={(e) => onDragStart(e, node.id)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onSelect(node.id);
          }
          // Arrow key navigation for moving nodes
          if (onMoveNode && isSelected) {
            const step = e.shiftKey ? 20 : 5;
            switch (e.key) {
              case "ArrowUp":
                e.preventDefault();
                onMoveNode(node.id, 0, -step);
                break;
              case "ArrowDown":
                e.preventDefault();
                onMoveNode(node.id, 0, step);
                break;
              case "ArrowLeft":
                e.preventDefault();
                onMoveNode(node.id, -step, 0);
                break;
              case "ArrowRight":
                e.preventDefault();
                onMoveNode(node.id, step, 0);
                break;
            }
          }
        }}
        aria-label={`${node.label} node, status: ${statusLabels[node.status]}`}
      >
        {/* Header */}
        <div className="flex items-center justify-between gap-2 mb-2">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <div className={cn("p-1.5 rounded-md shrink-0", config.bgClass)}>
              <Icon size={16} className={config.colorClass} />
            </div>
            <span className="font-medium text-foreground text-sm truncate">
              {node.label}
            </span>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            {/* Status Badge */}
            <span
              className={cn(
                "text-[10px] px-1.5 py-0.5 rounded-full font-medium flex items-center gap-1",
                statusBadgeColors[node.status]
              )}
            >
              {node.status === "running" && (
                <Loader2 size={10} className="animate-spin" />
              )}
              {statusLabels[node.status]}
            </span>
            
            {/* Compact Toggle */}
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="h-5 w-5 opacity-60 hover:opacity-100"
                  onClick={(e) => {
                    e.stopPropagation();
                    setIsCompact(!isCompact);
                  }}
                >
                  {isCompact ? <Maximize2 size={12} /> : <Minimize2 size={12} />}
                </Button>
              </TooltipTrigger>
              <TooltipContent side="top">
                {isCompact ? "Expand" : "Compact"}
              </TooltipContent>
            </Tooltip>

            <Button
              variant="ghost"
              size="icon-sm"
              className="h-5 w-5 opacity-60 hover:opacity-100"
              onClick={(e) => {
                e.stopPropagation();
              }}
            >
              <MoreHorizontal size={12} />
            </Button>
          </div>
        </div>

        {/* Description */}
        {node.description && !isCompact && (
          <p className="text-xs text-muted-foreground mb-2 line-clamp-2">
            {node.description}
          </p>
        )}

        {/* Schema Loading State */}
        {schemaLoading && (
          <div className="mb-2 space-y-1.5">
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-3/4" />
          </div>
        )}

        {/* Schema Error State */}
        {schemaError && (
          <div className="mb-2 p-2 rounded-md bg-destructive/10 border border-destructive/30">
            <div className="flex items-start gap-2">
              <AlertCircle size={14} className="text-destructive shrink-0 mt-0.5" />
              <div className="min-w-0">
                <p className="text-xs font-medium text-destructive">Schema Error</p>
                <p className="text-[10px] text-destructive/80 mt-0.5 break-words">
                  {schemaError}
                </p>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-5 px-1.5 text-[10px] text-destructive hover:bg-destructive/10 mt-1"
                  onClick={(e) => {
                    e.stopPropagation();
                    // Retry logic would go here
                  }}
                >
                  Retry
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* Output Preview */}
        {hasOutput && !isCompact && (
          <div className="mb-2">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] text-muted-foreground uppercase tracking-wide">
                Output
              </span>
              <div className="flex items-center gap-1">
                {node.status === "running" && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        className="h-4 w-4"
                        onClick={(e) => {
                          e.stopPropagation();
                          setScrollLock(!scrollLock);
                        }}
                      >
                        {scrollLock ? (
                          <Lock size={10} className="text-primary" />
                        ) : (
                          <Unlock size={10} className="text-muted-foreground" />
                        )}
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent side="top">
                      {scrollLock ? "Scroll locked" : "Scroll unlocked"}
                    </TooltipContent>
                  </Tooltip>
                )}
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      className="h-4 w-4"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleCopyOutput(fullOutput);
                      }}
                    >
                      {copied ? (
                        <Check size={10} className="text-success" />
                      ) : (
                        <Copy size={10} />
                      )}
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent side="top">Copy output</TooltipContent>
                </Tooltip>
              </div>
            </div>
            <div
              ref={outputRef}
              className="p-2 rounded-md bg-background/50 border border-border text-[10px] font-mono text-muted-foreground max-h-16 overflow-y-auto"
            >
              {outputPreview}
              {isOutputTruncated && "..."}
            </div>
            {isOutputTruncated && (
              <Button
                variant="ghost"
                size="sm"
                className="w-full h-5 text-[10px] mt-1"
                onClick={(e) => {
                  e.stopPropagation();
                  setOutputDialogOpen(true);
                }}
              >
                View full output
              </Button>
            )}
          </div>
        )}

        {/* Type Badge & Run Button */}
        <div className="flex items-center justify-between gap-2">
          <span
            className={cn(
              "text-[10px] px-2 py-0.5 rounded-full font-mono",
              config.bgClass,
              config.colorClass
            )}
          >
            {config.label}
          </span>
          
          {/* Run Button - Always visible, disabled when running */}
          {onRunNode && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant={isRunning ? "ghost" : "default"}
                  size="sm"
                  className={cn(
                    "h-6 px-2 gap-1 text-[10px]",
                    isRunning && "opacity-50 cursor-not-allowed"
                  )}
                  onClick={(e) => {
                    e.stopPropagation();
                    if (canRun) onRunNode(node.id);
                  }}
                  disabled={isRunning}
                >
                  {isRunning ? (
                    <Loader2 size={12} className="animate-spin" />
                  ) : (
                    <Play size={12} />
                  )}
                  {isRunning ? "Running" : "Run"}
                </Button>
              </TooltipTrigger>
              <TooltipContent side="bottom">
                {isRunning ? "Node is currently running" : "Run this node"}
              </TooltipContent>
            </Tooltip>
          )}
        </div>

        {/* Connection Ports */}
        <div className="absolute -left-2 top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-secondary border-2 border-muted-foreground/50 hover:border-primary hover:bg-primary/20 transition-colors cursor-crosshair" />
        <div className="absolute -right-2 top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-secondary border-2 border-muted-foreground/50 hover:border-primary hover:bg-primary/20 transition-colors cursor-crosshair" />

        {/* Resize Handle (only when expanded) */}
        {!isCompact && (
          <div
            className={cn(
              "absolute -right-1 top-1/2 -translate-y-1/2 w-2 h-8 flex items-center justify-center",
              "cursor-ew-resize opacity-0 hover:opacity-100 transition-opacity",
              "group-hover:opacity-60"
            )}
            onMouseDown={handleResizeStart}
          >
            <GripHorizontal size={10} className="text-muted-foreground rotate-90" />
          </div>
        )}
      </div>

      {/* Full Output Dialog */}
      <Dialog open={outputDialogOpen} onOpenChange={setOutputDialogOpen}>
        <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center justify-between">
              <span className="flex items-center gap-2">
                <Icon size={18} className={config.colorClass} />
                {node.label} - Output
              </span>
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5"
                onClick={() => handleCopyOutput(fullOutput)}
              >
                {copied ? <Check size={14} /> : <Copy size={14} />}
                {copied ? "Copied!" : "Copy all"}
              </Button>
            </DialogTitle>
          </DialogHeader>
          <ScrollArea className="flex-1 max-h-[60vh]">
            <pre className="p-4 text-sm font-mono text-foreground whitespace-pre-wrap break-words bg-muted/30 rounded-lg">
              {fullOutput}
            </pre>
          </ScrollArea>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default CanvasNode;
