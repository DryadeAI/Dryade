// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// ExecutionHistoryCard.tsx
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { ArrowRight, Clock, Play } from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { executionsApi, plansApi, getErrorMessage } from "@/services/api";
import type { ExecutionSummary, ExecutionStatus } from "@/types/execution";

interface ExecutionHistoryCardProps {
  maxItems?: number;
  className?: string;
}

const statusConfig: Record<ExecutionStatus, { color: string; pulseClass?: string }> = {
  running: { color: "bg-primary", pulseClass: "animate-pulse" },
  completed: { color: "bg-success" },
  failed: { color: "bg-destructive" },
  cancelled: { color: "bg-amber-500" },
};

const formatDuration = (ms?: number): string => {
  if (!ms) return "-";
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  const minutes = Math.floor(ms / 60000);
  const seconds = Math.floor((ms % 60000) / 1000);
  return `${minutes}m ${seconds}s`;
};

const formatScenarioName = (name: string): string => {
  return name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
};

const ExecutionHistoryCard = ({
  maxItems = 5,
  className,
}: ExecutionHistoryCardProps) => {
  const navigate = useNavigate();
  const [executions, setExecutions] = useState<ExecutionSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Use ref to track executions for interval check without causing re-renders
  const executionsRef = useRef<ExecutionSummary[]>([]);

  const loadExecutions = useCallback(async (showLoading = true) => {
    try {
      if (showLoading) {
        setIsLoading(true);
      }
      setError(null);

      // Fetch both scenario executions and plans in parallel
      const [scenarioResponse, plansResponse] = await Promise.all([
        executionsApi.list({ limit: maxItems }).catch(() => ({ executions: [] as ExecutionSummary[] })),
        plansApi.getPlans({ limit: 10 }).catch(() => ({ plans: [] as Array<{ id: number; name: string; status: string }>, total: 0 })),
      ]);

      // Tag scenario executions with source
      const scenarioExecs: ExecutionSummary[] = scenarioResponse.executions.map(e => ({
        ...e,
        source: 'scenario' as const,
      }));

      // Fetch plan executions for recently executed plans
      const planExecs: ExecutionSummary[] = [];
      const executedPlans = (plansResponse.plans || []).filter(
        (p) => p.status === 'executing' || p.status === 'completed' || p.status === 'failed'
      );

      // Only fetch details for up to 5 most recent executed plans to avoid N+1
      for (const plan of executedPlans.slice(0, 5)) {
        try {
          const results = await plansApi.getResults(plan.id);
          for (const r of results) {
            planExecs.push({
              id: 0, // Plan executions don't have a numeric id in this context
              execution_id: r.id,
              scenario_name: plan.name || `Plan #${plan.id}`,
              status: (r.status === 'executing' ? 'running' : r.status === 'timeout' ? 'failed' : r.status) as ExecutionStatus,
              started_at: r.started_at || new Date().toISOString(),
              duration_ms: r.duration_ms,
              source: 'plan' as const,
              _plan_id: plan.id,
            });
          }
        } catch {
          // Skip plans whose executions fail to load
        }
      }

      // Merge and sort by start time, keeping running ones at top
      const all = [...scenarioExecs, ...planExecs];
      const sorted = all.sort((a, b) => {
        if (a.status === 'running' && b.status !== 'running') return -1;
        if (a.status !== 'running' && b.status === 'running') return 1;
        return new Date(b.started_at).getTime() - new Date(a.started_at).getTime();
      }).slice(0, maxItems);

      setExecutions(sorted);
      executionsRef.current = sorted;
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      if (showLoading) {
        setIsLoading(false);
      }
    }
  }, [maxItems]);

  // Initial load
  useEffect(() => {
    loadExecutions();
  }, [loadExecutions]);

  // Polling for running executions (separate effect to avoid infinite loop)
  useEffect(() => {
    const interval = setInterval(() => {
      // Check ref instead of state to avoid dependency issues
      if (executionsRef.current.some(e => e.status === 'running')) {
        loadExecutions(false); // Don't show loading spinner on poll
      }
    }, 10000);

    return () => clearInterval(interval);
  }, [loadExecutions]);

  if (isLoading) {
    return (
      <div className={cn("glass-card p-5", className)}>
        <div className="flex items-center justify-between mb-4">
          <Skeleton className="h-6 w-40" />
          <Skeleton className="h-4 w-20" />
        </div>
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={cn("glass-card p-5", className)}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-display font-semibold text-foreground">Recent Executions</h2>
        </div>
        <div className="p-4 rounded-lg bg-destructive/10 text-sm text-destructive">
          {error}
        </div>
      </div>
    );
  }

  return (
    <div className={cn("glass-card p-5", className)}>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-display font-semibold text-foreground">Recent Executions</h2>
        <Link
          to="/workspace/executions"
          className="text-sm text-primary hover:underline flex items-center gap-1"
        >
          View all <ArrowRight size={14} />
        </Link>
      </div>

      {/* Execution list with custom scrollbar */}
      {executions.length === 0 ? (
        <div className="p-4 rounded-lg bg-secondary/30 text-sm text-muted-foreground text-center">
          <Play className="w-8 h-8 mx-auto mb-2 text-muted-foreground/50" />
          No executions yet
        </div>
      ) : (
        <ScrollArea className="h-[280px] -mx-2 px-2">
          <div className="space-y-2">
            {executions.map((execution) => {
              const config = statusConfig[execution.status];
              const isRunning = execution.status === 'running';

              return (
                <button
                  key={`${execution.source || 'scenario'}-${execution.execution_id}`}
                  onClick={() => {
                    if (execution._plan_id) {
                      navigate(`/workspace/workflows?planId=${execution._plan_id}`);
                    } else {
                      navigate(`/workspace/executions/${execution.execution_id}`);
                    }
                  }}
                  className={cn(
                    "w-full flex items-center gap-3 p-3 rounded-lg text-left",
                    "bg-secondary/30 hover:bg-secondary/50 transition-all duration-fast",
                    "group"
                  )}
                >
                  {/* Status dot */}
                  <div
                    className={cn(
                      "w-2.5 h-2.5 rounded-full shrink-0",
                      config.color,
                      config.pulseClass
                    )}
                  />

                  {/* Scenario name and time */}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground truncate group-hover:text-primary transition-colors">
                      {formatScenarioName(execution.scenario_name)}
                      {execution.source === 'plan' && (
                        <span className="ml-1.5 text-[10px] font-medium text-muted-foreground bg-secondary/50 px-1 py-0.5 rounded">
                          Plan
                        </span>
                      )}
                    </p>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <span>
                        {formatDistanceToNow(new Date(execution.started_at), { addSuffix: true })}
                      </span>
                      {!isRunning && (
                        <>
                          <span className="text-muted-foreground/50">·</span>
                          <span className="flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            {formatDuration(execution.duration_ms)}
                          </span>
                        </>
                      )}
                      {isRunning && (
                        <span className="text-primary font-medium">Running...</span>
                      )}
                    </div>
                  </div>

                  {/* Arrow on hover */}
                  <ArrowRight
                    size={14}
                    className="text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity"
                  />
                </button>
              );
            })}
          </div>
        </ScrollArea>
      )}
    </div>
  );
};

export default ExecutionHistoryCard;
