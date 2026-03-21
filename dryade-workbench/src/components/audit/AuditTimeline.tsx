// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// AuditTimeline.tsx - Timeline view with node cards and vertical connectors
// Phase 66-05: Workflow Execution Visibility

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { formatDuration } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  CheckCircle2,
  Circle,
  XCircle,
  SkipForward,
  Clock,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import type { NodeResult } from "@/types/execution";

interface AuditTimelineProps {
  nodes: NodeResult[];
  className?: string;
}

type NodeStatus = 'completed' | 'failed' | 'skipped';

const statusConfig: Record<NodeStatus, {
  icon: typeof Circle;
  color: string;
  bgColor: string;
  lineColor: string;
}> = {
  completed: {
    icon: CheckCircle2,
    color: "text-success",
    bgColor: "bg-success/10",
    lineColor: "bg-success",
  },
  failed: {
    icon: XCircle,
    color: "text-destructive",
    bgColor: "bg-destructive/10",
    lineColor: "bg-destructive",
  },
  skipped: {
    icon: SkipForward,
    color: "text-muted-foreground",
    bgColor: "bg-muted/50",
    lineColor: "bg-muted",
  },
};

const formatOutput = (output: unknown): string => {
  if (typeof output === 'string') return output;
  if (output === null || output === undefined) return '';
  try {
    return JSON.stringify(output, null, 2);
  } catch {
    return String(output);
  }
};

const AuditTimeline = ({ nodes, className }: AuditTimelineProps) => {
  const { t } = useTranslation('audit');
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());

  const toggleNode = (nodeId: string) => {
    setExpandedNodes(prev => {
      const next = new Set(prev);
      if (next.has(nodeId)) {
        next.delete(nodeId);
      } else {
        next.add(nodeId);
      }
      return next;
    });
  };

  const expandAll = () => {
    setExpandedNodes(new Set(nodes.map(n => n.node_id)));
  };

  const collapseAll = () => {
    setExpandedNodes(new Set());
  };

  return (
    <div className={cn("space-y-4", className)}>
      {/* Controls */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-foreground">{t('timeline.title')}</h2>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={expandAll}>
            {t('timeline.expandAll')}
          </Button>
          <Button variant="ghost" size="sm" onClick={collapseAll}>
            {t('timeline.collapseAll')}
          </Button>
        </div>
      </div>

      {/* Timeline */}
      <div className="relative pl-8">
        {/* Vertical line */}
        <div className="absolute left-3 top-0 bottom-0 w-0.5 bg-border" />

        <div className="space-y-4">
          {nodes.map((node, index) => {
            const status = node.status as NodeStatus;
            const config = statusConfig[status] || statusConfig.completed;
            const StatusIcon = config.icon;
            const isExpanded = expandedNodes.has(node.node_id);
            const output = formatOutput(node.output);
            const hasOutput = output.length > 0;

            return (
              <div key={node.node_id} className="relative">
                {/* Timeline dot */}
                <div
                  className={cn(
                    "absolute -left-5 top-4 w-4 h-4 rounded-full border-2 border-background",
                    "flex items-center justify-center z-10",
                    config.bgColor
                  )}
                >
                  <StatusIcon className={cn("w-2.5 h-2.5", config.color)} />
                </div>

                {/* Node card */}
                <Collapsible
                  open={isExpanded}
                  onOpenChange={() => { if (hasOutput) toggleNode(node.node_id); }}
                >
                  <div className={cn(
                    "rounded-lg border transition-colors",
                    config.bgColor,
                    isExpanded && "ring-1 ring-primary/20"
                  )}>
                    <CollapsibleTrigger asChild>
                      <button className={cn("w-full p-4 text-left", hasOutput && "cursor-pointer")} aria-expanded={hasOutput ? isExpanded : undefined} aria-disabled={!hasOutput}>
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            {/* Step number */}
                            <span
                              className={cn(
                                "w-7 h-7 rounded-full flex items-center justify-center text-sm font-medium",
                                status === 'completed' && "bg-success text-success-foreground",
                                status === 'failed' && "bg-destructive text-destructive-foreground",
                                status === 'skipped' && "bg-muted text-muted-foreground"
                              )}
                            >
                              {index + 1}
                            </span>

                            {/* Node name */}
                            <div>
                              <p className="font-medium text-foreground">{node.node_id}</p>
                              {node.duration_ms && (
                                <p className="text-xs text-muted-foreground flex items-center gap-1 mt-0.5">
                                  <Clock className="w-3 h-3" />
                                  {formatDuration(node.duration_ms)}
                                </p>
                              )}
                            </div>
                          </div>

                          <div className="flex items-center gap-2">
                            <Badge variant="outline" className={cn("text-xs", config.color)}>
                              {status}
                            </Badge>
                            {hasOutput && (
                              isExpanded ? (
                                <ChevronUp className="w-4 h-4 text-muted-foreground" aria-hidden="true" />
                              ) : (
                                <ChevronDown className="w-4 h-4 text-muted-foreground" aria-hidden="true" />
                              )
                            )}
                          </div>
                        </div>
                      </button>
                    </CollapsibleTrigger>

                    <CollapsibleContent>
                      {node.error ? (
                        <div className="px-4 pb-4">
                          <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/30">
                            <p className="text-sm text-destructive font-medium">{t('timeline.error')}</p>
                            <p className="text-sm text-destructive/80 mt-1">{node.error}</p>
                          </div>
                        </div>
                      ) : hasOutput ? (
                        <div className="px-4 pb-4">
                          <div className="max-h-64 overflow-auto">
                            <pre className="p-3 rounded-lg bg-background/50 text-sm font-mono whitespace-pre-wrap break-words">
                              {output}
                            </pre>
                          </div>
                        </div>
                      ) : null}
                    </CollapsibleContent>
                  </div>
                </Collapsible>

                {/* Connector line segment (colored based on status) */}
                {index < nodes.length - 1 && (
                  <div
                    className={cn(
                      "absolute -left-3 top-8 w-0.5 h-8",
                      config.lineColor
                    )}
                  />
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default AuditTimeline;
