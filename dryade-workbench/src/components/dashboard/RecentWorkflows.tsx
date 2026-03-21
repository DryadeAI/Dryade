// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";
import { Workflow, CheckCircle2, Loader2, XCircle, Circle, ArrowRight } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";

type WorkflowStatus = 'idle' | 'running' | 'success' | 'error';

interface WorkflowItem {
  id: string;
  name: string;
  status: WorkflowStatus;
  lastRun: string;
  nodes: number;
}

interface RecentWorkflowsProps {
  workflows?: WorkflowItem[];
  isLoading?: boolean;
}

const statusConfig: Record<WorkflowStatus, { icon: typeof Circle; color: string; label: string }> = {
  idle: { icon: Circle, color: "text-muted-foreground", label: "Idle" },
  running: { icon: Loader2, color: "text-primary", label: "Running" },
  success: { icon: CheckCircle2, color: "text-success", label: "Success" },
  error: { icon: XCircle, color: "text-destructive", label: "Error" },
};

const defaultWorkflows: WorkflowItem[] = [
  { id: '1', name: 'Data Pipeline v2', status: 'success', lastRun: '2 min ago', nodes: 8 },
  { id: '2', name: 'Customer Analysis', status: 'running', lastRun: 'Running...', nodes: 5 },
  { id: '3', name: 'Report Generator', status: 'error', lastRun: '15 min ago', nodes: 12 },
];

const RecentWorkflows = ({ workflows = defaultWorkflows, isLoading = false }: RecentWorkflowsProps) => {
  if (isLoading) {
    return (
      <div className="glass-card p-5">
        <div className="flex items-center justify-between mb-4">
          <Skeleton className="h-6 w-36" />
          <Skeleton className="h-4 w-16" />
        </div>
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="flex items-center gap-3 p-2">
              <Skeleton className="w-5 h-5 rounded" />
              <div className="flex-1">
                <Skeleton className="h-4 w-3/4 mb-1" />
                <Skeleton className="h-3 w-1/2" />
              </div>
              <Skeleton className="h-5 w-16 rounded-full" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  const isEmpty = workflows.length === 0;

  return (
    <div className="glass-card p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-foreground">Recent Workflows</h2>
        <Link
          to="/workspace/workflows"
          className="text-xs text-muted-foreground hover:text-primary flex items-center gap-1 transition-colors"
        >
          View all <ArrowRight size={10} />
        </Link>
      </div>

      {isEmpty ? (
        <div className="text-center py-8">
          <Workflow size={32} className="mx-auto text-muted-foreground/50 mb-2" />
          <p className="text-sm text-muted-foreground">No workflows yet</p>
          <Link
            to="/workspace/workflows"
            className="text-xs text-primary hover:underline mt-1 inline-block"
          >
            Create your first workflow
          </Link>
        </div>
      ) : (
        <div className="space-y-1">
          {workflows.map((workflow) => {
            const config = statusConfig[workflow.status];
            const StatusIcon = config.icon;

            return (
              <Link
                key={workflow.id}
                to={`/workspace/workflows?id=${workflow.id}`}
                className="flex items-center gap-3 p-2 rounded-lg hover:bg-secondary/50 transition-colors group"
              >
                <StatusIcon
                  size={16}
                  className={cn(
                    config.color,
                    workflow.status === 'running' && "animate-spin"
                  )}
                />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-foreground truncate group-hover:text-primary transition-colors">
                    {workflow.name}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {workflow.nodes} nodes · {workflow.lastRun}
                  </p>
                </div>
                <span
                  className={cn(
                    "text-xs font-medium px-2 py-0.5 rounded-full",
                    workflow.status === 'success' && "bg-success/10 text-success",
                    workflow.status === 'running' && "bg-primary/10 text-primary",
                    workflow.status === 'error' && "bg-destructive/10 text-destructive",
                    workflow.status === 'idle' && "bg-muted text-muted-foreground"
                  )}
                >
                  {config.label}
                </span>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default RecentWorkflows;
