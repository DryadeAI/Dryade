// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// ExecutionTimeline - Vertical timeline of executions
// Based on COMPONENTS-4.md specification

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { formatDistanceToNow } from "date-fns";
import {
  Play,
  CheckCircle2,
  XCircle,
  Clock,
  Star,
  DollarSign,
  Loader2,
  ChevronDown,
} from "lucide-react";

interface ExecutionResult {
  id: number | string;
  execution_id: string;
  start_time: string;
  end_time?: string;
  status: "executing" | "completed" | "failed";
  duration_ms?: number;
  total_cost?: number;
  user_feedback_rating?: number;
}

interface ExecutionTimelineProps {
  executions: ExecutionResult[];
  selectedId?: number | string;
  onSelect: (execution: ExecutionResult) => void;
  onLoadMore?: () => void;
  hasMore?: boolean;
  loading?: boolean;
  className?: string;
}

const statusConfig: Record<
  ExecutionResult["status"],
  { icon: typeof Clock; color: string; bgColor: string; label: string }
> = {
  executing: { icon: Play, color: "text-primary", bgColor: "bg-primary/10", label: "Executing" },
  completed: { icon: CheckCircle2, color: "text-success", bgColor: "bg-success/10", label: "Completed" },
  failed: { icon: XCircle, color: "text-destructive", bgColor: "bg-destructive/10", label: "Failed" },
};

const formatDuration = (ms?: number): string => {
  if (!ms) return "-";
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`;
};

const ExecutionTimeline = ({
  executions,
  selectedId,
  onSelect,
  onLoadMore,
  hasMore = false,
  loading = false,
  className,
}: ExecutionTimelineProps) => {
  if (executions.length === 0 && !loading) {
    return (
      <div
        className={cn(
          "flex flex-col items-center justify-center py-8 text-center",
          className
        )}
      >
        <Clock className="w-10 h-10 text-muted-foreground mb-3" aria-hidden="true" />
        <p className="text-sm text-muted-foreground">No executions yet</p>
      </div>
    );
  }

  return (
    <ScrollArea className={cn("h-full", className)}>
      <div className="relative pl-6 pr-2 py-2">
        {/* Timeline line */}
        <div className="absolute left-3 top-0 bottom-0 w-0.5 bg-border" />

        {/* Executions */}
        <div className="space-y-3">
          {executions.map((execution, idx) => {
            const config = statusConfig[execution.status];
            const StatusIcon = config.icon;
            const isSelected = selectedId === execution.id;

            return (
              <button
                key={execution.id}
                onClick={() => onSelect(execution)}
                className={cn(
                  "relative w-full text-left p-3 rounded-lg border transition-all",
                  isSelected
                    ? "border-primary bg-primary/5 shadow-sm"
                    : "border-border hover:border-primary/50 hover:bg-muted/30"
                )}
              >
                {/* Timeline dot */}
                <div
                  className={cn(
                    "absolute -left-3 top-4 w-4 h-4 rounded-full border-2 border-background flex items-center justify-center",
                    config.bgColor
                  )}
                >
                  <StatusIcon
                    className={cn(
                      "w-2.5 h-2.5",
                      config.color,
                      execution.status === "executing" && "motion-safe:animate-pulse"
                    )}
                  />
                </div>

                {/* Content */}
                <div className="space-y-2">
                  {/* Header */}
                  <div className="flex items-center justify-between gap-2">
                    <Badge
                      variant="outline"
                      className={cn("text-xs capitalize", config.color, config.bgColor)}
                    >
                      {execution.status}
                    </Badge>
                    <span className="text-[10px] text-muted-foreground">
                      {formatDistanceToNow(new Date(execution.start_time), {
                        addSuffix: true,
                      })}
                    </span>
                  </div>

                  {/* Execution ID */}
                  <p className="text-xs font-mono text-muted-foreground truncate">
                    {execution.execution_id}
                  </p>

                  {/* Stats */}
                  <div className="flex items-center gap-3 text-xs text-muted-foreground">
                    {/* Duration */}
                    <span className="flex items-center gap-1">
                      <Clock className="w-3 h-3" aria-hidden="true" />
                      {formatDuration(execution.duration_ms)}
                    </span>

                    {/* Cost */}
                    {execution.total_cost !== undefined && (
                      <span className="flex items-center gap-1">
                        <DollarSign className="w-3 h-3" aria-hidden="true" />
                        {execution.total_cost.toFixed(4)}
                      </span>
                    )}

                    {/* Rating */}
                    {execution.user_feedback_rating !== undefined && (
                      <span className="flex items-center gap-0.5">
                        <Star className="w-3 h-3 fill-amber-400 text-amber-400" aria-hidden="true" />
                        {execution.user_feedback_rating}
                      </span>
                    )}
                  </div>
                </div>
              </button>
            );
          })}

          {/* Loading */}
          {loading && (
            <div className="flex items-center justify-center py-4">
              <Loader2 className="w-5 h-5 motion-safe:animate-spin text-muted-foreground" aria-hidden="true" />
            </div>
          )}

          {/* Load More */}
          {hasMore && !loading && onLoadMore && (
            <Button
              variant="ghost"
              size="sm"
              className="w-full"
              onClick={onLoadMore}
            >
              <ChevronDown className="w-4 h-4 mr-1" aria-hidden="true" />
              Load more
            </Button>
          )}
        </div>
      </div>
    </ScrollArea>
  );
};

export default ExecutionTimeline;
