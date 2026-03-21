// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  ChevronDown,
  ChevronRight,
  Loader2,
  CheckCircle2,
  XCircle,
  Clock,
  Copy,
  Check,
} from "lucide-react";
import type { ToolCall } from "@/types/api";

interface ToolExecutionPanelProps {
  toolCall: ToolCall;
  className?: string;
}

const statusConfig = {
  pending: { icon: Clock, color: "text-muted-foreground", label: "Pending", spin: false },
  executing: { icon: Loader2, color: "text-primary", label: "Executing", spin: true },
  complete: { icon: CheckCircle2, color: "text-success", label: "Complete", spin: false },
  error: { icon: XCircle, color: "text-destructive", label: "Error", spin: false },
};

const ToolExecutionPanel = ({ toolCall, className }: ToolExecutionPanelProps) => {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  const config = statusConfig[toolCall.status];
  const StatusIcon = config.icon;

  const handleCopyResult = async () => {
    if (!toolCall.result) return;
    try {
      await navigator.clipboard.writeText(toolCall.result);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error("Failed to copy:", err);
    }
  };

  return (
    <div
      className={cn(
        "rounded-lg border overflow-hidden",
        toolCall.status === "error" ? "border-destructive/30 bg-destructive/5" : "border-border bg-secondary/30",
        className
      )}
    >
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-secondary/50 transition-colors"
      >
        {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <StatusIcon
          size={14}
          className={cn(config.color, config.spin && "animate-spin")}
        />
        <span className="font-mono text-sm text-foreground">{toolCall.tool}</span>
        <span className={cn("text-xs ml-auto", config.color)}>{config.label}</span>
        {toolCall.duration_ms && (
          <span className="text-xs text-muted-foreground font-mono">
            {toolCall.duration_ms}ms
          </span>
        )}
      </button>

      {/* Expanded Content */}
      {expanded && (
        <div className="px-3 pb-3 space-y-2 border-t border-border/50">
          {/* Arguments */}
          <div className="pt-2">
            <p className="text-xs text-muted-foreground mb-1">Arguments:</p>
            <pre className="text-xs font-mono bg-background/50 rounded p-2 overflow-x-auto">
              {JSON.stringify(toolCall.args, null, 2)}
            </pre>
          </div>

          {/* Result */}
          {toolCall.result && (
            <div>
              <div className="flex items-center justify-between mb-1">
                <p className="text-xs text-muted-foreground">Result:</p>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 px-2 text-xs"
                  onClick={handleCopyResult}
                >
                  {copied ? <Check size={12} /> : <Copy size={12} />}
                  {copied ? "Copied" : "Copy"}
                </Button>
              </div>
              <pre className="text-xs font-mono bg-background/50 rounded p-2 overflow-x-auto max-h-40">
                {toolCall.result}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default ToolExecutionPanel;
