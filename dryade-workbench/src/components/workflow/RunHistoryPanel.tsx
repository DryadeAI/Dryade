// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useEffect, useCallback } from "react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Clock,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Activity,
  AlertCircle,
} from "lucide-react";
import { executionsApi, plansApi } from "@/services/api";
import type { ExecutionSummary } from "@/types/execution";
import type { PlanExecution } from "@/types/extended-api";

function timeAgo(dateStr: string): string {
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (seconds < 0) return "just now";
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

function formatDuration(ms?: number): string {
  if (ms === undefined || ms === null) return "--";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

interface RunHistoryItem {
  id: string;
  status: string;
  startedAt: string;
  durationMs?: number;
  result?: unknown;
}

interface RunHistoryPanelProps {
  scenarioName?: string | null;
  planId?: number | null;
  currentExecutionId?: string | number | null;
  onViewResult?: (result: unknown) => void;
  className?: string;
}

export function RunHistoryPanel({
  scenarioName,
  planId,
  currentExecutionId,
  onViewResult,
  className,
}: RunHistoryPanelProps) {
  const [items, setItems] = useState<RunHistoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchHistory = useCallback(async () => {
    if (!scenarioName && !planId) {
      setItems([]);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      if (planId) {
        const executions: PlanExecution[] = await plansApi.getResults(planId);
        setItems(
          executions.slice(0, 10).map((e) => ({
            id: e.id,
            status: e.status,
            startedAt: e.started_at,
            durationMs: e.duration_ms,
            result: e.node_results,
          }))
        );
      } else if (scenarioName) {
        const { executions } = await executionsApi.list({
          scenario_name: scenarioName,
          limit: 10,
        });
        setItems(
          executions.map((e: ExecutionSummary) => ({
            id: e.execution_id,
            status: e.status,
            startedAt: e.started_at,
            durationMs: e.duration_ms,
            result: undefined, // Scenario list doesn't include result details
          }))
        );
      }
    } catch (err) {
      console.error("Failed to fetch run history:", err);
      setError("Failed to load history");
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [scenarioName, planId]);

  // Fetch when workflow/plan changes
  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  // Re-fetch when a new execution completes (currentExecutionId changes)
  useEffect(() => {
    if (currentExecutionId) {
      // Delay slightly so the backend has time to persist the result
      const timer = setTimeout(() => fetchHistory(), 1500);
      return () => clearTimeout(timer);
    }
  }, [currentExecutionId, fetchHistory]);

  // Don't render when nothing is selected
  if (!scenarioName && !planId) {
    return null;
  }

  const statusConfig: Record<string, {
    icon: typeof CheckCircle2;
    colorClass: string;
    bgClass: string;
    label: string;
  }> = {
    completed: { icon: CheckCircle2, colorClass: "text-success", bgClass: "bg-success/10", label: "Completed" },
    failed: { icon: XCircle, colorClass: "text-destructive", bgClass: "bg-destructive/10", label: "Failed" },
    running: { icon: Activity, colorClass: "text-blue-500", bgClass: "bg-blue-500/10", label: "Running" },
    executing: { icon: Activity, colorClass: "text-blue-500", bgClass: "bg-blue-500/10", label: "Running" },
    cancelled: { icon: AlertCircle, colorClass: "text-amber-500", bgClass: "bg-amber-500/10", label: "Cancelled" },
    timeout: { icon: AlertCircle, colorClass: "text-amber-500", bgClass: "bg-amber-500/10", label: "Timeout" },
  };

  return (
    <div className={cn("", className)}>
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2">
        <div className="flex items-center gap-2">
          <Clock size={14} className="text-muted-foreground" />
          <span className="text-sm font-medium text-foreground">Run History</span>
          {items.length > 0 && (
            <span className="text-xs px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground">
              {items.length}
            </span>
          )}
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6"
          onClick={fetchHistory}
          disabled={loading}
        >
          <RefreshCw size={12} className={cn(loading && "animate-spin")} />
        </Button>
      </div>

      {/* Content */}
      <div className="px-2 pb-2">
        {error && (
          <p className="text-xs text-destructive px-2 py-1">{error}</p>
        )}

        {!error && items.length === 0 && !loading && (
          <div className="flex flex-col items-center justify-center py-4 text-muted-foreground">
            <Clock size={20} className="mb-1.5 opacity-40" />
            <p className="text-xs">No executions yet</p>
          </div>
        )}

        {loading && items.length === 0 && (
          <div className="flex items-center justify-center py-4">
            <RefreshCw size={14} className="animate-spin text-muted-foreground" />
          </div>
        )}

        {items.length > 0 && (
          <div className="space-y-0.5">
            {items.map((item) => {
              const config = statusConfig[item.status] || statusConfig.cancelled;
              const Icon = config.icon;
              const isCurrent = currentExecutionId && String(item.id) === String(currentExecutionId);

              return (
                <div
                  key={item.id}
                  className={cn(
                    "flex items-center gap-2 px-2 py-1.5 rounded-md text-xs transition-colors",
                    "hover:bg-secondary/40",
                    isCurrent && "bg-primary/5 ring-1 ring-primary/20",
                    item.result && onViewResult && "cursor-pointer"
                  )}
                  onClick={() => {
                    if (item.result && onViewResult) {
                      onViewResult(item.result);
                    }
                  }}
                  title={item.result && onViewResult ? "Click to view result" : undefined}
                >
                  {/* Status icon */}
                  <div className={cn("p-1 rounded shrink-0", config.bgClass)}>
                    <Icon size={10} className={config.colorClass} />
                  </div>

                  {/* Status badge */}
                  <Badge
                    variant="outline"
                    className={cn(
                      "text-[10px] px-1.5 py-0 h-4 border-0",
                      config.bgClass,
                      config.colorClass
                    )}
                  >
                    {config.label}
                  </Badge>

                  {/* Duration */}
                  <span className="text-muted-foreground tabular-nums shrink-0">
                    {formatDuration(item.durationMs)}
                  </span>

                  {/* Spacer */}
                  <span className="flex-1" />

                  {/* Relative time */}
                  <span className="text-muted-foreground/70 shrink-0">
                    {timeAgo(item.startedAt)}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

export default RunHistoryPanel;
