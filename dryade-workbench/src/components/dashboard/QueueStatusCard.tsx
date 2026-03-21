// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { cn } from "@/lib/utils";
import { ListOrdered, Clock } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import type { QueueStatus } from "@/types/api";

interface QueueStatusCardProps {
  status?: QueueStatus;
  isLoading?: boolean;
}

const statusColors = {
  healthy: { bg: "bg-success/10", text: "text-success", label: "Healthy" },
  busy: { bg: "bg-warning/10", text: "text-warning", label: "Busy" },
  overloaded: { bg: "bg-destructive/10", text: "text-destructive", label: "Overloaded" },
};

const formatWaitTime = (ms: number): string => {
  if (ms < 1000) return `${ms}ms`;
  return `~${(ms / 1000).toFixed(1)}s`;
};

const QueueStatusCard = ({ status, isLoading = false }: QueueStatusCardProps) => {
  if (isLoading || !status) {
    return (
      <div className="glass-card p-5">
        <div className="flex items-center justify-between mb-4">
          <Skeleton className="h-6 w-28" />
          <Skeleton className="h-5 w-16 rounded-full" />
        </div>
        <div className="space-y-3">
          <div className="flex justify-between">
            <Skeleton className="h-4 w-16" />
            <Skeleton className="h-4 w-12" />
          </div>
          <div className="flex justify-between">
            <Skeleton className="h-4 w-20" />
            <Skeleton className="h-4 w-8" />
          </div>
        </div>
      </div>
    );
  }

  const config = statusColors[status.status];

  return (
    <div className="glass-card p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-foreground">Queue Status</h2>
        <span className={cn("text-xs font-medium px-2 py-0.5 rounded-full", config.bg, config.text)}>
          {config.label}
        </span>
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <ListOrdered size={14} />
            Active / Queued
          </div>
          <span className="text-sm font-mono text-foreground">
            {status.active} / {status.queued}
          </span>
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Clock size={14} />
            Wait time
          </div>
          <span className="text-sm font-mono text-foreground">
            {formatWaitTime(status.average_wait_ms)}
          </span>
        </div>

        {/* Queue usage bar */}
        <div className="pt-2">
          <div className="h-2 bg-secondary rounded-full overflow-hidden">
            <div
              className={cn(
                "h-full rounded-full transition-all",
                status.status === 'healthy' && "bg-success",
                status.status === 'busy' && "bg-warning",
                status.status === 'overloaded' && "bg-destructive"
              )}
              style={{ width: `${Math.min((status.queued / status.max_queue_size) * 100, 100)}%` }}
            />
          </div>
          <p className="text-xs text-muted-foreground mt-1 text-right">
            {status.queued} / {status.max_queue_size}
          </p>
        </div>
      </div>
    </div>
  );
};

export default QueueStatusCard;
