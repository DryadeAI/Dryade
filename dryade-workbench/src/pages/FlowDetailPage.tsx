// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import PageBreadcrumb from "@/components/shared/PageBreadcrumb";
import EmptyState from "@/components/shared/EmptyState";
import { flowsApi } from "@/services/api";
import { Play, Pause, RotateCcw, Settings, History, AlertCircle, CheckCircle2, XCircle, Clock, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { useTranslation } from 'react-i18next';
import type { FlowDetail, FlowExecution, FlowCheckpoint } from "@/types/api";

const FlowDetailPage = () => {
  const { t } = useTranslation('workflows');
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [flow, setFlow] = useState<FlowDetail | null>(null);
  const [executions, setExecutions] = useState<FlowExecution[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [currentExecution, setCurrentExecution] = useState<FlowExecution | null>(null);
  const [isExecuting, setIsExecuting] = useState(false);

  useEffect(() => {
    const loadFlow = async () => {
      if (!id) return;
      setIsLoading(true);
      try {
        const data = await flowsApi.getFlow(id);
        setFlow(data);
        // No executions loaded yet - show empty state
        setExecutions([]);
      } catch (error) {
        console.error("Failed to load flow:", error);
        toast.error(t('flowDetail.toast.loadFailed'));
      } finally {
        setIsLoading(false);
      }
    };
    loadFlow();
  }, [id]);

  const handleExecute = async () => {
    if (!id) return;
    setIsExecuting(true);
    try {
      const execution = await flowsApi.executeFlow(id);
      setCurrentExecution(execution);
      setExecutions((prev) => [execution, ...prev]);
      toast.success(t('flowDetail.toast.executeSuccess'));
    } catch (error) {
      toast.error(t('flowDetail.toast.executeFailed'));
    } finally {
      setIsExecuting(false);
    }
  };

  const handleStop = async () => {
    if (!currentExecution) return;
    try {
      await flowsApi.stopExecution(currentExecution.id);
      toast.info(t('flowDetail.toast.stopSuccess'));
    } catch (error) {
      toast.error(t('flowDetail.toast.stopFailed'));
    }
  };

  const getStatusLabel = (status: string): string => {
    switch (status) {
      case "complete": return t('flowDetail.status.complete');
      case "running": return t('flowDetail.status.running');
      case "error": return t('flowDetail.status.error');
      default: return t('flowDetail.status.pending');
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "complete": return <CheckCircle2 className="w-4 h-4 text-success" aria-hidden="true" />;
      case "running": return <Clock className="w-4 h-4 text-primary motion-safe:animate-pulse" aria-hidden="true" />;
      case "error": return <XCircle className="w-4 h-4 text-destructive" aria-hidden="true" />;
      default: return <Clock className="w-4 h-4 text-muted-foreground" aria-hidden="true" />;
    }
  };

  if (isLoading) {
    return (
      <div className="h-full overflow-auto p-6">
        <div className="max-w-5xl mx-auto space-y-6">
          <Skeleton className="h-5 w-48" />
          <div className="flex items-center gap-4">
            <Skeleton className="h-10 w-10 rounded-lg" />
            <div className="space-y-2">
              <Skeleton className="h-6 w-48" />
              <Skeleton className="h-4 w-32" />
            </div>
          </div>
          <Skeleton className="h-64" />
        </div>
      </div>
    );
  }

  if (!flow) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center space-y-4">
          <AlertCircle className="w-12 h-12 text-muted-foreground mx-auto" aria-hidden="true" />
          <h2 className="text-xl font-semibold">{t('flowDetail.flowNotFound')}</h2>
          <p className="text-muted-foreground">{t('flowDetail.flowNotFoundDescription')}</p>
          <Button onClick={() => navigate("/workspace/workflows")}>
            {t('flowDetail.backToWorkflows')}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto p-6">
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Breadcrumb */}
        <PageBreadcrumb
          items={[
            { label: t('flowDetail.breadcrumbWorkflows'), href: "/workspace/workflows" },
            { label: flow.name },
          ]}
        />

        {/* Header */}
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-semibold text-foreground">{flow.name}</h1>
              <Badge
                variant={flow.status === "complete" ? "default" : "secondary"}
                className={cn(flow.status === "complete" && "bg-success/10 text-success")}
              >
                {flow.status}
              </Badge>
            </div>
            <p className="text-muted-foreground mt-1">{flow.description || t('flowDetail.noDescription')}</p>
          </div>
          <div className="flex items-center gap-2">
            {currentExecution?.status === "running" ? (
              <Button variant="outline" onClick={handleStop}>
                <Pause className="w-4 h-4 mr-2" aria-hidden="true" />
                {t('flowDetail.stop')}
              </Button>
            ) : (
              <Button onClick={handleExecute} disabled={isExecuting}>
                <Play className="w-4 h-4 mr-2" aria-hidden="true" />
                {t('flowDetail.execute')}
              </Button>
            )}
            <Button variant="outline">
              <Settings className="w-4 h-4 mr-2" aria-hidden="true" />
              {t('flowDetail.configure')}
            </Button>
          </div>
        </div>

        {/* Current Execution */}
        {currentExecution && currentExecution.status === "running" && (
          <Card className="border-primary/50 bg-primary/5">
            <CardContent className="pt-6">
              <div className="flex items-center gap-3" role="status" aria-label="Execution in progress">
                <Loader2 className="w-5 h-5 text-primary motion-safe:animate-spin" aria-hidden="true" />
                <span className="font-medium">{t('flowDetail.executionInProgress')}</span>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Tabs */}
        <Tabs defaultValue="nodes" className="space-y-4">
          <TabsList>
            <TabsTrigger value="nodes">{t('flowDetail.nodesTab', { count: flow.nodes?.length || 0 })}</TabsTrigger>
            <TabsTrigger value="executions" className="gap-2">
              <History className="w-4 h-4" aria-hidden="true" />
              {t('flowDetail.executionsTab')}
            </TabsTrigger>
            <TabsTrigger value="checkpoints" className="gap-2">
              <RotateCcw className="w-4 h-4" aria-hidden="true" />
              {t('flowDetail.checkpointsTab')}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="nodes">
            <Card>
              <CardHeader>
                <CardTitle>{t('flowDetail.flowNodes')}</CardTitle>
                <CardDescription>{t('flowDetail.stepsInFlow')}</CardDescription>
              </CardHeader>
              <CardContent>
                {flow.nodes && flow.nodes.length > 0 ? (
                  <div className="space-y-3">
                    {flow.nodes.map((node, idx) => (
                      <div
                        key={node.id}
                        className="flex items-center gap-4 p-4 rounded-lg border border-border"
                      >
                        <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-sm font-medium">
                          {idx + 1}
                        </div>
                        <div className="flex-1">
                          <p className="font-medium">{node.label}</p>
                          <p className="text-sm text-muted-foreground">{node.type}</p>
                        </div>
                        {node.status && (
                          <span className="flex items-center gap-1.5">
                            {getStatusIcon(node.status)}
                            <span className="text-xs text-muted-foreground sr-only">{getStatusLabel(node.status)}</span>
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <EmptyState
                    variant="workflow"
                    title={t('flowDetail.noNodes')}
                    description="This workflow has no configured nodes yet."
                    size="sm"
                  />
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="executions">
            <Card>
              <CardHeader>
                <CardTitle>{t('flowDetail.executionHistory')}</CardTitle>
                <CardDescription>{t('flowDetail.recentExecutions')}</CardDescription>
              </CardHeader>
              <CardContent>
                <ScrollArea className="h-96">
                  {executions.length > 0 ? (
                    <div className="space-y-4">
                      {executions.map((exec) => (
                        <div
                          key={exec.id}
                          role="button"
                          tabIndex={0}
                          className="p-4 rounded-lg border border-border hover:border-primary/50 cursor-pointer transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                          onClick={() => setCurrentExecution(exec)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              setCurrentExecution(exec);
                            }
                          }}
                        >
                          <div className="flex items-center justify-between mb-2">
                            <Badge
                              variant={exec.status === "complete" ? "default" : exec.status === "running" ? "secondary" : "destructive"}
                              className={cn(exec.status === "complete" && "bg-success/10 text-success border-success/30")}
                            >
                              {exec.status}
                            </Badge>
                            <span className="text-xs text-muted-foreground">
                              {new Date(exec.started_at).toLocaleString()}
                            </span>
                          </div>
                          {exec.duration_ms && (
                            <p className="text-sm text-muted-foreground">
                              {t('flowDetail.duration', { seconds: (exec.duration_ms / 1000).toFixed(2) })}
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyState
                      variant="workflow"
                      title={t('flowDetail.noExecutionsYet')}
                      description={t('flowDetail.noExecutionsHint')}
                      action={{
                        label: t('flowDetail.execute'),
                        onClick: handleExecute,
                      }}
                      size="sm"
                    />
                  )}
                </ScrollArea>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="checkpoints">
            <Card>
              <CardHeader>
                <CardTitle>{t('flowDetail.checkpointsTitle')}</CardTitle>
                <CardDescription>{t('flowDetail.checkpointsDescription')}</CardDescription>
              </CardHeader>
              <CardContent>
                {currentExecution?.checkpoints && currentExecution.checkpoints.length > 0 ? (
                  <div className="space-y-4">
                    {currentExecution.checkpoints.map((cp: FlowCheckpoint) => (
                      <div
                        key={cp.id}
                        className="flex items-center justify-between p-4 rounded-lg border border-border"
                      >
                        <div>
                          <p className="font-medium">{cp.node_name}</p>
                          <p className="text-sm text-muted-foreground">
                            {new Date(cp.created_at).toLocaleString()}
                          </p>
                        </div>
                        <Button variant="outline" size="sm">
                          <RotateCcw className="w-4 h-4 mr-2" aria-hidden="true" />
                          {t('flowDetail.restore')}
                        </Button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <EmptyState
                    variant="default"
                    title={t('flowDetail.noCheckpoints')}
                    description="Run this workflow to create execution checkpoints for recovery."
                    size="sm"
                  />
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
};

export default FlowDetailPage;
