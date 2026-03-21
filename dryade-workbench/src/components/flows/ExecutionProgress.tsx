// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { cn } from "@/lib/utils";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { CheckCircle2, Circle, Loader2, XCircle, SkipForward } from "lucide-react";

type NodeStatus = "pending" | "running" | "completed" | "failed" | "skipped";

interface ExecutionNode {
  id: string;
  label: string;
  status: NodeStatus;
  startedAt?: string;
  completedAt?: string;
  error?: string;
}

interface ExecutionProgressProps {
  nodes: ExecutionNode[];
  currentNodeId?: string;
  className?: string;
}

const statusConfig: Record<
  NodeStatus,
  { icon: typeof Circle; color: string; bgColor: string; label: string }
> = {
  pending: {
    icon: Circle,
    color: "text-muted-foreground",
    bgColor: "bg-muted",
    label: "Pending",
  },
  running: {
    icon: Loader2,
    color: "text-primary",
    bgColor: "bg-primary/10",
    label: "Running",
  },
  completed: {
    icon: CheckCircle2,
    color: "text-success",
    bgColor: "bg-success/10",
    label: "Completed",
  },
  failed: {
    icon: XCircle,
    color: "text-destructive",
    bgColor: "bg-destructive/10",
    label: "Failed",
  },
  skipped: {
    icon: SkipForward,
    color: "text-muted-foreground",
    bgColor: "bg-muted/50",
    label: "Skipped",
  },
};

const ExecutionProgress = ({
  nodes,
  currentNodeId,
  className,
}: ExecutionProgressProps) => {
  const completedCount = nodes.filter(
    (n) => n.status === "completed" || n.status === "skipped"
  ).length;
  const progress = (completedCount / nodes.length) * 100;

  return (
    <div className={cn("space-y-4", className)}>
      {/* Overall progress */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">Overall Progress</span>
          <span className="font-medium">
            {completedCount}/{nodes.length} steps
          </span>
        </div>
        <Progress value={progress} className="h-2" />
      </div>

      {/* Node list */}
      <div className="space-y-2">
        {nodes.map((node, index) => {
          const config = statusConfig[node.status];
          const StatusIcon = config.icon;
          const isCurrent = node.id === currentNodeId;

          return (
            <div
              key={node.id}
              className={cn(
                "flex items-center gap-3 p-3 rounded-lg transition-colors",
                config.bgColor,
                isCurrent && "ring-2 ring-primary ring-offset-2 ring-offset-background"
              )}
            >
              {/* Step number */}
              <div
                className={cn(
                  "w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium",
                  node.status === "completed" && "bg-success text-success-foreground",
                  node.status === "running" && "bg-primary text-primary-foreground",
                  node.status === "failed" && "bg-destructive text-destructive-foreground",
                  (node.status === "pending" || node.status === "skipped") &&
                    "bg-muted text-muted-foreground"
                )}
              >
                {index + 1}
              </div>

              {/* Status icon */}
              <StatusIcon
                className={cn(
                  "w-4 h-4",
                  config.color,
                  node.status === "running" && "animate-spin"
                )}
              />

              {/* Node info */}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{node.label}</p>
                {node.error && (
                  <p className="text-xs text-destructive truncate">{node.error}</p>
                )}
              </div>

              {/* Status badge */}
              <Badge
                variant="outline"
                className={cn("text-xs", config.color)}
              >
                {config.label}
              </Badge>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default ExecutionProgress;
