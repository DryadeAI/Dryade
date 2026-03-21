// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Progress } from "@/components/ui/progress";
import NodeOutputAccordion from "./NodeOutputAccordion";
import {
  Play,
  Square,
  Clock,
  CheckCircle2,
  XCircle,
  AlertCircle,
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import type { ExecutionStatus } from "@/types/execution";

interface ExecutionNode {
  id: string;
  type: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  output?: string;
  error?: string;
}

interface ExecutionSidebarProps {
  scenarioName: string | null;
  status: ExecutionStatus | 'idle';
  nodes: ExecutionNode[];
  currentNodeId: string | null;
  startedAt: string | null;
  error: string | null;
  onCancel: () => void;
  onClose: () => void;
  className?: string;
}

const statusConfig: Record<ExecutionStatus | 'idle', { icon: typeof Clock; color: string; label: string }> = {
  idle: { icon: Clock, color: "text-muted-foreground", label: "Ready" },
  running: { icon: Play, color: "text-primary", label: "Running" },
  completed: { icon: CheckCircle2, color: "text-success", label: "Completed" },
  failed: { icon: XCircle, color: "text-destructive", label: "Failed" },
  cancelled: { icon: AlertCircle, color: "text-warning", label: "Cancelled" },
};

const ExecutionSidebar = ({
  scenarioName,
  status,
  nodes,
  currentNodeId,
  startedAt,
  error,
  onCancel,
  onClose,
  className,
}: ExecutionSidebarProps) => {
  const config = statusConfig[status];
  const StatusIcon = config.icon;

  const completedCount = nodes.filter(n => n.status === 'completed').length;
  const progress = nodes.length > 0 ? (completedCount / nodes.length) * 100 : 0;
  const isRunning = status === 'running';
  const isComplete = status === 'completed' || status === 'failed' || status === 'cancelled';

  return (
    <div className={cn("w-72 border-l border-border h-full hidden lg:flex flex-col bg-card/50", className)}>
      {/* Header */}
      <div className="p-4 border-b border-border">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <StatusIcon className={cn("w-5 h-5", config.color, isRunning && "animate-pulse")} />
            <span className="font-semibold text-foreground">Execution</span>
          </div>
          <Badge variant="outline" className={cn("text-xs", config.color)}>
            {config.label}
          </Badge>
        </div>

        {/* Scenario name */}
        {scenarioName && (
          <p className="text-sm font-medium text-foreground mb-2 truncate">
            {scenarioName.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
          </p>
        )}

        {/* Progress bar */}
        <div className="space-y-1">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>Progress</span>
            <span>{completedCount}/{nodes.length} steps</span>
          </div>
          <Progress value={progress} className="h-2" />
        </div>

        {/* Time info */}
        {startedAt && (
          <p className="text-xs text-muted-foreground mt-2">
            Started {formatDistanceToNow(new Date(startedAt), { addSuffix: true })}
          </p>
        )}
      </div>

      {/* Cancel button - prominent when running */}
      {isRunning && (
        <div className="p-4 border-b border-border">
          <Button
            variant="destructive"
            className="w-full gap-2"
            onClick={onCancel}
          >
            <Square size={16} />
            Cancel Execution
          </Button>
        </div>
      )}

      {/* Error display */}
      {error && (
        <div className="p-4 border-b border-destructive/30 bg-destructive/10">
          <p className="text-sm text-destructive font-medium">Error</p>
          <p className="text-xs text-destructive/80 mt-1">{error}</p>
        </div>
      )}

      {/* Node outputs */}
      <ScrollArea className="flex-1">
        <div className="p-4">
          <NodeOutputAccordion
            nodes={nodes}
            currentNodeId={currentNodeId}
          />
        </div>
      </ScrollArea>

      {/* Footer - show close button when complete */}
      {isComplete && (
        <div className="p-4 border-t border-border">
          <Button
            variant="outline"
            className="w-full"
            onClick={onClose}
          >
            Close & Return to Chat
          </Button>
        </div>
      )}
    </div>
  );
};

export default ExecutionSidebar;
