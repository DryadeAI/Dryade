// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// AuditHeader.tsx - Header component for execution audit page
// Phase 66-05: Workflow Execution Visibility

import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { formatDuration } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import {
  CheckCircle2,
  XCircle,
  AlertCircle,
  Clock,
  RotateCcw,
  Download,
  FileJson,
  FileText,
  LayoutList,
  GitBranch,
} from "lucide-react";
import { format } from "date-fns";
import type { ExecutionDetail, ExecutionStatus } from "@/types/execution";

interface AuditHeaderProps {
  execution: ExecutionDetail;
  viewMode: 'timeline' | 'graph';
  onViewModeChange: (mode: 'timeline' | 'graph') => void;
  onRunAgain: () => void;
  className?: string;
}

const statusConfig: Record<ExecutionStatus, {
  icon: typeof CheckCircle2;
  color: string;
  bgColor: string;
  labelKey: string;
}> = {
  running: { icon: Clock, color: "text-primary", bgColor: "bg-primary/10", labelKey: "header.status.running" },
  completed: { icon: CheckCircle2, color: "text-success", bgColor: "bg-success/10", labelKey: "header.status.completed" },
  failed: { icon: XCircle, color: "text-destructive", bgColor: "bg-destructive/10", labelKey: "header.status.failed" },
  cancelled: { icon: AlertCircle, color: "text-warning", bgColor: "bg-warning/10", labelKey: "header.status.cancelled" },
};

const formatScenarioName = (name: string): string => {
  return name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
};

const AuditHeader = ({
  execution,
  viewMode,
  onViewModeChange,
  onRunAgain,
  className,
}: AuditHeaderProps) => {
  const { t } = useTranslation('audit');
  const config = statusConfig[execution.status];
  const StatusIcon = config.icon;

  const handleDownloadJSON = () => {
    const data = JSON.stringify(execution, null, 2);
    const blob = new Blob([data], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `execution-${execution.execution_id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleDownloadMarkdown = () => {
    const lines = [
      `# Execution: ${formatScenarioName(execution.scenario_name)}`,
      '',
      `**Status:** ${execution.status}`,
      `**Execution ID:** ${execution.execution_id}`,
      `**Started:** ${format(new Date(execution.started_at), 'PPpp')}`,
      execution.completed_at ? `**Completed:** ${format(new Date(execution.completed_at), 'PPpp')}` : '',
      `**Duration:** ${formatDuration(execution.duration_ms)}`,
      '',
      '## Inputs',
      '```json',
      JSON.stringify(execution.inputs, null, 2),
      '```',
      '',
      '## Node Results',
      '',
      ...execution.node_results.map((node, i) => [
        `### ${i + 1}. ${node.node_id}`,
        `**Status:** ${node.status}`,
        node.duration_ms ? `**Duration:** ${formatDuration(node.duration_ms)}` : '',
        '',
        node.output ? `\`\`\`\n${typeof node.output === 'string' ? node.output : JSON.stringify(node.output, null, 2)}\n\`\`\`` : '',
        node.error ? `**Error:** ${node.error}` : '',
        '',
      ]).flat(),
      '## Final Result',
      '```json',
      JSON.stringify(execution.final_result, null, 2),
      '```',
    ].filter(Boolean);

    const blob = new Blob([lines.join('\n')], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `execution-${execution.execution_id}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className={cn("space-y-4", className)}>
      {/* Breadcrumb */}
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <Link to="/workspace">{t('header.breadcrumb.dashboard')}</Link>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <Link to="/workspace/executions">{t('header.breadcrumb.executions')}</Link>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage className="font-mono text-xs">
              {execution.execution_id.slice(0, 8)}...
            </BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      {/* Summary bar */}
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 p-4 rounded-lg bg-card border">
        {/* Left: Status and info */}
        <div className="flex items-center gap-4">
          <div className={cn("p-3 rounded-lg", config.bgColor)}>
            <StatusIcon className={cn("w-6 h-6", config.color)} />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-foreground">
              {formatScenarioName(execution.scenario_name)}
            </h1>
            <div className="flex items-center gap-3 mt-1 text-sm text-muted-foreground">
              <Badge variant="outline" className={cn(config.color)}>
                {t(config.labelKey)}
              </Badge>
              <span className="flex items-center gap-1">
                <Clock className="w-3.5 h-3.5" />
                {formatDuration(execution.duration_ms)}
              </span>
              <span>
                {format(new Date(execution.started_at), 'MMM d, yyyy HH:mm')}
              </span>
            </div>
          </div>
        </div>

        {/* Right: Actions */}
        <div className="flex items-center gap-2">
          {/* View mode toggle */}
          <div className="flex items-center border rounded-lg p-1">
            <Button
              variant={viewMode === 'timeline' ? 'secondary' : 'ghost'}
              size="sm"
              className="gap-1.5"
              onClick={() => onViewModeChange('timeline')}
            >
              <LayoutList className="w-4 h-4" />
              {t('header.viewTimeline')}
            </Button>
            <Button
              variant={viewMode === 'graph' ? 'secondary' : 'ghost'}
              size="sm"
              className="gap-1.5"
              onClick={() => onViewModeChange('graph')}
            >
              <GitBranch className="w-4 h-4" />
              {t('header.viewGraph')}
            </Button>
          </div>

          {/* Run Again */}
          <Button variant="outline" className="gap-2" onClick={onRunAgain}>
            <RotateCcw className="w-4 h-4" />
            {t('header.runAgain')}
          </Button>

          {/* Download */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" className="gap-2">
                <Download className="w-4 h-4" />
                {t('header.download')}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={handleDownloadJSON}>
                <FileJson className="w-4 h-4 mr-2" />
                {t('header.downloadJSON')}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={handleDownloadMarkdown}>
                <FileText className="w-4 h-4 mr-2" />
                {t('header.downloadMarkdown')}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </div>
  );
};

export default AuditHeader;
