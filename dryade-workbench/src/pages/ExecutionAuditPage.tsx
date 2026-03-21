// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// ExecutionAuditPage.tsx - Full execution audit page
// Phase 66-05: Workflow Execution Visibility

import { useEffect, useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useParams, useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import EmptyState from "@/components/shared/EmptyState";
import AuditHeader from "@/components/audit/AuditHeader";
import AuditTimeline from "@/components/audit/AuditTimeline";
import AuditGraphView from "@/components/audit/AuditGraphView";
import { executionsApi, getErrorMessage } from "@/services/api";
import type { ExecutionDetail } from "@/types/execution";
import { ArrowLeft, RefreshCw } from "lucide-react";

type ViewMode = 'timeline' | 'graph';

const ExecutionAuditPage = () => {
  const { t } = useTranslation('audit');
  const { executionId } = useParams<{ executionId: string }>();
  const navigate = useNavigate();

  const [execution, setExecution] = useState<ExecutionDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('timeline');

  const loadExecution = useCallback(async () => {
    if (!executionId) return;

    try {
      setIsLoading(true);
      setError(null);
      const data = await executionsApi.get(executionId);
      setExecution(data);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  }, [executionId]);

  useEffect(() => {
    loadExecution();
  }, [loadExecution]);

  const handleRunAgain = useCallback(async () => {
    if (!execution) return;

    // Navigate to chat and trigger the scenario
    // For now, just navigate - the actual trigger would need to be wired up
    navigate('/workspace/chat', {
      state: {
        triggerScenario: execution.scenario_name,
        inputs: execution.inputs,
      }
    });
  }, [execution, navigate]);

  if (isLoading) {
    return (
      <div className="p-6 space-y-6">
        <Skeleton className="h-6 w-64" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (error || !execution) {
    return (
      <div className="p-6 space-y-6">
        <Button variant="ghost" onClick={() => navigate(-1)} className="gap-2">
          <ArrowLeft className="w-4 h-4" />
          {t('page.back')}
        </Button>

        <EmptyState
          variant="default"
          title={error ? t('page.errorLoading') : t('page.notFound')}
          description={error || t('page.notFoundDescription', { id: executionId })}
          action={{
            label: t('page.retry'),
            onClick: loadExecution,
          }}
          size="md"
        />
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Header with summary and actions */}
      <AuditHeader
        execution={execution}
        viewMode={viewMode}
        onViewModeChange={setViewMode}
        onRunAgain={handleRunAgain}
      />

      {/* Inputs section (collapsible or compact) */}
      {Object.keys(execution.inputs).length > 0 && (
        <div className="p-4 rounded-lg bg-card border">
          <h3 className="text-sm font-medium text-muted-foreground mb-2">{t('page.inputs')}</h3>
          <pre className="text-sm font-mono bg-muted/50 p-3 rounded overflow-x-auto">
            {JSON.stringify(execution.inputs, null, 2)}
          </pre>
        </div>
      )}

      {/* Main content: Timeline or Graph */}
      {viewMode === 'timeline' ? (
        <AuditTimeline nodes={execution.node_results} />
      ) : (
        <AuditGraphView nodes={execution.node_results} />
      )}

      {/* Final result */}
      {execution.final_result && (
        <div className="p-4 rounded-lg bg-card border">
          <h3 className="text-sm font-medium text-muted-foreground mb-2">{t('page.finalResult')}</h3>
          <pre className="text-sm font-mono bg-muted/50 p-3 rounded overflow-x-auto overflow-y-auto max-h-64">
            {typeof execution.final_result === 'string'
              ? execution.final_result
              : JSON.stringify(execution.final_result, null, 2)}
          </pre>
        </div>
      )}

      {/* Error display */}
      {execution.error && (
        <div className="p-4 rounded-lg bg-destructive/10 border border-destructive/30">
          <h3 className="text-sm font-medium text-destructive mb-2">{t('page.executionError')}</h3>
          <p className="text-sm text-destructive/80">{execution.error}</p>
        </div>
      )}
    </div>
  );
};

export default ExecutionAuditPage;
