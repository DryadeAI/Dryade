// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { formatMs, formatNumber } from "@/lib/format";
import {
  Workflow,
  MessageSquare,
  Play,
  Clock,
  CheckCircle2,
  AlertCircle,
  ArrowRight,
  Activity,
  Bot,
  RefreshCw,
  XCircle,
  WifiOff,
} from "lucide-react";
import { agentsApi, getErrorMessage, healthApi, metricsApi, queueApi, workflowsApi } from "@/services/api";
import { PluginSlot } from "@/plugins/slots";
import type { HealthStatus } from "@/types/api";
import type { RecentRequest } from "@/types/extended-api";
import type { WorkflowListItem } from "@/types/workflow";
import StatsCard from "@/components/shared/StatsCard";
import ExecutionHistoryCard from "@/components/dashboard/ExecutionHistoryCard";
import { ScrollArea } from "@/components/ui/scroll-area";
import EmptyState from "@/components/shared/EmptyState";

type LoadingState = "loading" | "loaded" | "partial" | "disconnected";

const timeAgo = (isoTimestamp: string): string => {
  const timestamp = new Date(isoTimestamp).getTime();
  if (Number.isNaN(timestamp)) return "unknown";

  const diffSeconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000));
  if (diffSeconds < 60) return `${diffSeconds}s ago`;

  const diffMinutes = Math.floor(diffSeconds / 60);
  if (diffMinutes < 60) return `${diffMinutes}m ago`;

  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours}h ago`;

  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}d ago`;
};

// Helper to safely settle a promise with a default value
async function safeResolve<T>(promise: Promise<T>, fallback: T): Promise<T> {
  try {
    return await promise;
  } catch {
    return fallback;
  }
}

const DashboardPage = () => {
  const { t } = useTranslation('dashboard');
  const { t: tCommon } = useTranslation('common');
  const [loadingState, setLoadingState] = useState<LoadingState>("loading");
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [activeAgents, setActiveAgents] = useState(0);
  const [queuePending, setQueuePending] = useState(0);
  const [totalRequests, setTotalRequests] = useState(0);
  const [successRate, setSuccessRate] = useState<number | null>(null);
  const [workflows, setWorkflows] = useState<WorkflowListItem[]>([]);
  const [totalWorkflows, setTotalWorkflows] = useState(0);
  const [recentRequests, setRecentRequests] = useState<RecentRequest[]>([]);
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null);

  const loadDashboard = useCallback(async () => {
    setLoadingState("loading");

    // Use safeResolve so each API call fails independently
    const [healthResponse, agentsResponse, queueResponse, latencyResponse, workflowsResponse, recentResponse] =
      await Promise.all([
        safeResolve(healthApi.getHealth(), null),
        safeResolve(agentsApi.getAgents(), { agents: [], total: 0 }),
        safeResolve(queueApi.getStatus(), { active: 0, queued: 0, rejected_total: 0, max_concurrent: 0, max_queue_size: 0, average_wait_ms: 0, status: 'healthy' as const }),
        safeResolve(metricsApi.getLatency(), { avg_ms: 0, p50_ms: 0, p95_ms: 0, p99_ms: 0, total_requests: 0 }),
        safeResolve(workflowsApi.getWorkflows(), { workflows: [], total: 0 }),
        safeResolve(metricsApi.getLatencyRecent(10), []),
      ]);

    setHealth(healthResponse);
    setActiveAgents(agentsResponse.total);
    setQueuePending(queueResponse.queued);
    setTotalRequests(latencyResponse.total_requests ?? 0);
    setWorkflows((workflowsResponse.workflows ?? []).slice(0, 4));
    setTotalWorkflows(workflowsResponse.total ?? (workflowsResponse.workflows ?? []).length);
    setRecentRequests((recentResponse ?? []).slice(0, 5));

    const recentTotal = (recentResponse ?? []).length;
    const recentSuccesses = (recentResponse ?? []).filter((r) => r.status === "success").length;
    setSuccessRate(recentTotal > 0 ? (recentSuccesses / recentTotal) * 100 : null);

    // Determine state: all null/empty = disconnected, some data = partial, all data = loaded
    const hasAnyData = healthResponse || agentsResponse.total > 0 || (workflowsResponse.workflows ?? []).length > 0;
    if (!hasAnyData && !healthResponse) {
      setLoadingState("disconnected");
    } else {
      setLoadingState("loaded");
    }
    setLastRefreshed(new Date());
  }, []);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  const handleRefresh = () => {
    void loadDashboard();
  };

  // Get greeting based on time
  const hour = new Date().getHours();
  const greeting = hour < 12 ? t('greeting.morning') : hour < 18 ? t('greeting.afternoon') : t('greeting.evening');

  const apiStatusLabel = useMemo(() => {
    if (loadingState === "disconnected") return { label: "Disconnected", icon: WifiOff, className: "text-muted-foreground" };
    if (!health) return { label: "Unknown", icon: AlertCircle, className: "text-muted-foreground" };
    if (health.status === "healthy") return { label: "Operational", icon: CheckCircle2, className: "text-success" };
    if (health.status === "degraded") return { label: "Degraded", icon: AlertCircle, className: "text-amber-500" };
    return { label: "Unhealthy", icon: XCircle, className: "text-destructive" };
  }, [health, loadingState]);

  const queueStatusLabel = useMemo(() => {
    if (queuePending === 0) return { label: "Empty", icon: CheckCircle2, className: "text-success" };
    return { label: `${queuePending} Pending`, icon: AlertCircle, className: "text-amber-500" };
  }, [queuePending]);

  const ApiStatusIcon = apiStatusLabel.icon;
  const QueueStatusIcon = queueStatusLabel.icon;

  if (loadingState === "loading") {
    return (
      <div className="p-6 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <Skeleton className="h-9 w-48 mb-2" />
            <Skeleton className="h-4 w-64" />
          </div>
          <Skeleton className="h-10 w-32" />
        </div>
        <Skeleton className="h-32 w-full lg:w-2/3" />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            <Skeleton className="h-64" />
          </div>
          <Skeleton className="h-64" />
        </div>
      </div>
    );
  }

  return (
    <main className="p-6 space-y-6" data-testid="dashboard-container">
      {/* Disconnected Banner */}
      {loadingState === "disconnected" && (
        <div className="flex items-center gap-3 p-4 rounded-lg border border-muted bg-muted/30">
          <WifiOff size={18} className="text-muted-foreground shrink-0" aria-hidden="true" />
          <div className="flex-1">
            <p className="text-sm font-medium text-foreground">{t('disconnected.title')}</p>
            <p className="text-xs text-muted-foreground">
              {t('disconnected.message')}
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={handleRefresh}>
            <RefreshCw size={14} className="mr-1" aria-hidden="true" />
            {tCommon('actions.retry')}
          </Button>
        </div>
      )}

      {/* Header */}
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-display font-bold text-foreground">{greeting}</h1>
          <p className="text-muted-foreground text-sm mt-1">
            {t('subtitle')}
            {lastRefreshed && (
              <span className="ml-2 text-xs text-muted-foreground/70">
                — updated {lastRefreshed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={handleRefresh}>
            <RefreshCw size={14} className="mr-2" aria-hidden="true" />
            {t('labels.viewMetrics', { defaultValue: 'Refresh' })}
          </Button>
          <Button variant="hero" asChild>
            <Link to="/workspace/chat">
              <MessageSquare size={16} className="mr-2" aria-hidden="true" />
              {t('quickActions.chatWithAgent')}
            </Link>
          </Button>
        </div>
      </header>

      {/* Hero Stat */}
      <StatsCard
        variant="hero"
        accentColor="primary"
        title={t('stats.totalRequests')}
        value={totalRequests.toLocaleString()}
        icon={<Activity size={24} />}
        trend={
          totalRequests > 0
            ? {
                direction: "neutral",
                value: "Total",
              }
            : undefined
        }
        className="w-full lg:w-2/3 border-t-2 border-primary/50 hover:glow-box-sm"
        valueClassName="glow-text-md"
      />

      {/* Secondary Stats Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatsCard
          title={t('stats.successRate')}
          value={successRate === null ? "—" : `${formatNumber(successRate, 1)}%`}
          icon={<CheckCircle2 size={18} />}
          accentColor="primary"
          trend={
            successRate !== null
              ? {
                  direction: successRate >= 95 ? "up" : "down",
                  value: `${formatNumber(Math.abs(successRate - 95), 1)}%`,
                  label: "from target",
                  isPositive: successRate >= 95,
                }
              : undefined
          }
          className="border-t-2 border-primary/50 hover:glow-box-sm"
          valueClassName="glow-text-md"
        />

        <StatsCard
          title={t('stats.activeAgents')}
          value={activeAgents}
          icon={<Bot size={18} />}
          accentColor="secondary"
          trend={{
            direction: "neutral",
            value: "Stable",
          }}
          className="border-t-2 border-primary/40"
        />

        <StatsCard
          title={t('stats.queueStatus')}
          value={queuePending}
          icon={<Clock size={18} />}
          accentColor="tertiary"
          trend={
            queuePending === 0
              ? {
                  direction: "down",
                  value: "Empty",
                  isPositive: true,
                }
              : {
                  direction: "up",
                  value: `${queuePending} pending`,
                  isPositive: false,
                }
          }
          className="border-t-2 border-primary/30"
        />

        <StatsCard
          title={t('stats.workflows')}
          value={totalWorkflows}
          icon={<Workflow size={18} />}
          trend={
            totalWorkflows > 0
              ? {
                  direction: "neutral",
                  value: `${workflows.length} recent`,
                }
              : undefined
          }
          className="border-t-2 border-primary/25"
        />
      </div>

      {/* Recent Activity Section - Execution history prominent */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Execution History - Primary activity view */}
        <ExecutionHistoryCard maxItems={5} />

        {/* Recent Requests */}
        <div className="glass-card p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-display font-semibold text-foreground">{t('sections.recentRequests')}</h2>
            <Link
              to="/workspace/metrics"
              className="text-sm text-primary hover:underline flex items-center gap-1"
            >
              {t('labels.viewMetrics')} <ArrowRight size={14} aria-hidden="true" />
            </Link>
          </div>
          <ScrollArea className="h-[280px] -mx-2 px-2">
            <div className="space-y-2">
              {recentRequests.length === 0 ? (
                <EmptyState
                  variant="default"
                  title={t('empty.noRequests')}
                  description={t('empty.noRequestsDescription', { defaultValue: 'Request activity will appear here once you start using the platform.' })}
                  size="sm"
                />
              ) : (
                recentRequests.map((request) => (
                  <div
                    key={request.id}
                    className="flex items-center justify-between p-3 rounded-lg hover:bg-secondary/30 transition-all duration-fast"
                  >
                    <div className="flex items-center gap-3">
                      {request.status === "success" ? (
                        <CheckCircle2 size={14} className="text-success shrink-0" aria-hidden="true" />
                      ) : (
                        <XCircle size={14} className="text-destructive shrink-0" aria-hidden="true" />
                      )}
                      <div>
                        <p className="text-sm font-medium text-foreground">
                          {request.mode.toUpperCase()} {t('labels.request')}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {request.status === "success" ? t('labels.completed') : t('labels.failed')} • {formatMs(request.latency_ms)}
                        </p>
                      </div>
                    </div>
                    <span className="text-xs text-muted-foreground">{timeAgo(request.timestamp)}</span>
                  </div>
                ))
              )}
            </div>
          </ScrollArea>
        </div>
      </div>

      {/* Workflow Templates and System Status */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Workflow Templates */}
        <div className="lg:col-span-2 glass-card p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-display font-semibold text-foreground">{t('sections.workflowTemplates')}</h2>
            <Link
              to="/workspace/workflows"
              className="text-sm text-primary hover:underline flex items-center gap-1"
            >
              {t('labels.viewAllWorkflows')} <ArrowRight size={14} aria-hidden="true" />
            </Link>
          </div>
          <div className="space-y-3">
            {workflows.length === 0 ? (
              <EmptyState
                variant="workflow"
                title={t('empty.noWorkflows')}
                description={t('empty.noWorkflowsDescription')}
                size="sm"
              />
            ) : (
              workflows.map((workflow) => (
              <div
                key={workflow.id}
                className="flex items-center justify-between p-3 rounded-lg bg-secondary/30 hover:bg-secondary/50 transition-all duration-fast"
              >
                <div className="flex items-center gap-3">
                  {workflow.status === "published" ? (
                      <CheckCircle2 size={14} className="text-success shrink-0" aria-hidden="true" />
                    ) : workflow.status === "draft" ? (
                      <AlertCircle size={14} className="text-amber-500 shrink-0" aria-hidden="true" />
                    ) : (
                      <XCircle size={14} className="text-muted-foreground shrink-0" aria-hidden="true" />
                    )}
                  <div>
                    <p className="font-medium text-foreground">{workflow.name}</p>
                    <p className="text-xs text-muted-foreground">
                      v{workflow.version} • {workflow.execution_count.toLocaleString()} executions • updated{" "}
                      {timeAgo(workflow.updated_at)}
                    </p>
                  </div>
                </div>
                <Button variant="ghost" size="sm" asChild aria-label={`Open workflow ${workflow.name}`}>
                  <Link to={`/workspace/workflows?workflowId=${workflow.id}`}>
                    <Play size={14} aria-hidden="true" />
                  </Link>
                </Button>
              </div>
            ))
            )}
          </div>
        </div>

        {/* System Status */}
        <div className="glass-card p-5">
          <h2 className="text-lg font-display font-semibold text-foreground mb-4">{t('sections.systemStatus')}</h2>
          <div className="space-y-4">
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">{t('labels.api')}</span>
                <span className={cn("flex items-center gap-1.5 font-medium", apiStatusLabel.className)}>
                  <ApiStatusIcon size={12} aria-hidden="true" /> {apiStatusLabel.label}
                </span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">{t('labels.agents')}</span>
                <span className="flex items-center gap-1.5 text-success font-medium">
                  <CheckCircle2 size={12} aria-hidden="true" /> {activeAgents} {t('status.registered')}
                </span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">{t('labels.queue')}</span>
                <span className={cn("flex items-center gap-1.5 font-medium", queueStatusLabel.className)}>
                  <QueueStatusIcon size={12} aria-hidden="true" /> {queueStatusLabel.label}
                </span>
              </div>
            </div>
            <Link
              to="/workspace/health"
              className="block text-sm text-primary hover:underline"
            >
              {t('labels.viewSystemHealth')}
            </Link>
          </div>

          {/* Quick Access */}
          <div className="mt-6 pt-4 border-t border-border">
            <h3 className="text-sm font-medium text-foreground mb-3">{t('sections.quickAccess')}</h3>
            <div className="space-y-2">
              <Button
                variant="outline"
                size="sm"
                className="w-full justify-start transition-all duration-fast hover:border-primary/50"
                asChild
              >
                <Link to="/workspace/chat">
                  <MessageSquare size={16} className="mr-2" aria-hidden="true" />
                  {t('quickActions.newConversation')}
                </Link>
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="w-full justify-start transition-all duration-fast hover:border-accent-secondary/50"
                asChild
              >
                <Link to="/workspace/workflows">
                  <Workflow size={16} className="mr-2" aria-hidden="true" />
                  {t('quickActions.createWorkflow')}
                </Link>
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* Plugin dashboard widgets */}
      <PluginSlot
        name="dashboard-widget"
        className="col-span-full"
      />
    </main>
  );
};

export default DashboardPage;
