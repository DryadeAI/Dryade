// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { CheckCircle2, XCircle, Clock, ChevronDown, Copy, Download, FileJson } from "lucide-react";
import { cn } from "@/lib/utils";
import { useState, useMemo } from "react";
import { toast } from "sonner";

interface NodeResult {
  node_id: string;
  status: string;
  output?: unknown;
  duration_ms?: number;
  error?: string;
}

// Supports both SSE event structure and API ExecutionDetail structure
interface ExecutionResult {
  // Common fields
  execution_id?: string;
  error?: string;

  // SSE event structure (from workflow_complete)
  output?: unknown;
  executed_nodes?: string[];
  state?: Record<string, unknown>;

  // API ExecutionDetail structure
  id?: number;
  scenario_name?: string;
  status?: string;
  started_at?: string;
  completed_at?: string;
  duration_ms?: number;
  node_results?: NodeResult[];
  final_result?: unknown;
  inputs?: Record<string, unknown>;
}

interface ExecutionResultModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  result: ExecutionResult | null;
  workflowName?: string;
  status?: "success" | "error" | "running" | "idle";
}

export const ExecutionResultModal = ({
  open,
  onOpenChange,
  result,
  workflowName,
  status: externalStatus,
}: ExecutionResultModalProps) => {
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());

  // Normalize result to consistent structure
  const normalizedData = useMemo(() => {
    if (!result) return null;

    // Determine the final output (SSE uses output, API uses final_result)
    const finalOutput = result.output ?? result.final_result;

    // Determine status: use external status > result.status > infer from error
    const effectiveStatus = externalStatus || result.status || (result.error ? "error" : "completed");

    // Extract node results
    // SSE: Build from state keys ending in _output
    // API: Use node_results directly
    let nodeResults: NodeResult[] = [];

    if (result.node_results && result.node_results.length > 0) {
      // API format - use directly
      nodeResults = result.node_results;
    } else if (result.state) {
      // SSE format - extract from state
      const executedNodes = result.executed_nodes || [];
      for (const nodeId of executedNodes) {
        const outputKey = `${nodeId}_output`;
        if (outputKey in result.state) {
          nodeResults.push({
            node_id: nodeId,
            status: "completed",
            output: result.state[outputKey],
          });
        }
      }
      // Also check for any _output keys not in executed_nodes
      for (const [key, value] of Object.entries(result.state)) {
        if (key.endsWith("_output") && value !== undefined) {
          const nodeId = key.replace("_output", "");
          if (!nodeResults.some(n => n.node_id === nodeId)) {
            nodeResults.push({
              node_id: nodeId,
              status: "completed",
              output: value,
            });
          }
        }
      }
    }

    return {
      finalOutput,
      effectiveStatus,
      nodeResults,
      executionId: result.execution_id,
      error: result.error || (result.state?.error as string | undefined),
      durationMs: result.duration_ms,
      startedAt: result.started_at,
      completedAt: result.completed_at,
      inputs: result.inputs,
      scenarioName: result.scenario_name,
    };
  }, [result, externalStatus]);

  if (!result || !normalizedData) return null;

  const toggleNode = (nodeId: string) => {
    setExpandedNodes((prev) => {
      const next = new Set(prev);
      if (next.has(nodeId)) {
        next.delete(nodeId);
      } else {
        next.add(nodeId);
      }
      return next;
    });
  };

  const formatDuration = (ms?: number) => {
    if (!ms) return "N/A";
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    return `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`;
  };

  const formatWorkflowName = (name?: string) => {
    if (!name) return "Workflow";
    return name
      .replace(/_/g, " ")
      .replace(/\b\w/g, (c) => c.toUpperCase());
  };

  const getStatusIcon = (status?: string) => {
    switch (status) {
      case "completed":
      case "success":
        return <CheckCircle2 size={16} className="text-green-500" />;
      case "failed":
      case "error":
        return <XCircle size={16} className="text-red-500" />;
      default:
        return <Clock size={16} className="text-muted-foreground" />;
    }
  };

  const getStatusColor = (status?: string) => {
    switch (status) {
      case "completed":
      case "success":
        return "bg-green-500/10 text-green-500 hover:bg-green-500/20";
      case "failed":
      case "error":
        return "bg-red-500/10 text-red-500 hover:bg-red-500/20";
      default:
        return "bg-muted text-muted-foreground";
    }
  };

  const copyToClipboard = async (data: unknown) => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(data, null, 2));
      toast.success("Copied to clipboard");
    } catch {
      toast.error("Failed to copy");
    }
  };

  const downloadResult = () => {
    const blob = new Blob([JSON.stringify(result, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${workflowName || "workflow"}-result-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success("Result downloaded");
  };

  const displayName = workflowName || normalizedData.scenarioName;
  const { finalOutput, effectiveStatus, nodeResults, executionId, error, durationMs, startedAt, completedAt, inputs } = normalizedData;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-[500px] sm:w-[600px] p-0 flex flex-col">
        <SheetHeader className="px-6 py-4 border-b shrink-0">
          <div className="flex items-center justify-between">
            <SheetTitle className="flex items-center gap-2">
              <FileJson size={18} className="text-primary" />
              Execution Result
            </SheetTitle>
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={() => copyToClipboard(result)}
                title="Copy result"
              >
                <Copy size={14} />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={downloadResult}
                title="Download result"
              >
                <Download size={14} />
              </Button>
            </div>
          </div>
          <SheetDescription className="flex items-center gap-2">
            {formatWorkflowName(displayName)}
            <Badge className={cn("text-xs", getStatusColor(effectiveStatus))}>
              {effectiveStatus}
            </Badge>
            {durationMs && (
              <span className="text-xs text-muted-foreground">
                {formatDuration(durationMs)}
              </span>
            )}
          </SheetDescription>
        </SheetHeader>

        <ScrollArea className="flex-1 px-6">
          <div className="py-4 space-y-4">
            {/* Final Result */}
            {finalOutput !== undefined && finalOutput !== null && (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <h4 className="text-sm font-medium flex items-center gap-2">
                    {getStatusIcon(effectiveStatus)}
                    Final Output
                  </h4>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 text-xs"
                    onClick={() => copyToClipboard(finalOutput)}
                  >
                    <Copy size={12} className="mr-1" />
                    Copy
                  </Button>
                </div>
                <pre className="p-3 rounded-md bg-muted/50 text-xs overflow-x-auto whitespace-pre-wrap font-mono max-h-64 overflow-y-auto">
                  {typeof finalOutput === "string"
                    ? finalOutput
                    : JSON.stringify(finalOutput, null, 2)}
                </pre>
              </div>
            )}

            {/* Error */}
            {error && (
              <div className="space-y-2">
                <h4 className="text-sm font-medium text-red-500 flex items-center gap-2">
                  <XCircle size={14} />
                  Error
                </h4>
                <pre className="p-3 rounded-md bg-red-500/10 text-xs text-red-500 overflow-x-auto whitespace-pre-wrap font-mono">
                  {error}
                </pre>
              </div>
            )}

            {/* Node Results */}
            {nodeResults.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-sm font-medium">
                  Node Results ({nodeResults.length})
                </h4>
                <div className="space-y-1">
                  {nodeResults.map((node) => (
                    <Collapsible
                      key={node.node_id}
                      open={expandedNodes.has(node.node_id)}
                      onOpenChange={() => toggleNode(node.node_id)}
                    >
                      <CollapsibleTrigger className="flex items-center justify-between w-full p-2 rounded-md hover:bg-muted/50 transition-colors">
                        <div className="flex items-center gap-2">
                          {getStatusIcon(node.status)}
                          <span className="text-sm font-medium">
                            {node.node_id}
                          </span>
                          {node.duration_ms && (
                            <span className="text-xs text-muted-foreground">
                              {formatDuration(node.duration_ms)}
                            </span>
                          )}
                        </div>
                        <ChevronDown
                          size={14}
                          className={cn(
                            "text-muted-foreground transition-transform",
                            expandedNodes.has(node.node_id) && "rotate-180"
                          )}
                        />
                      </CollapsibleTrigger>
                      <CollapsibleContent>
                        <div className="pl-6 pb-2 space-y-2">
                          {node.output !== undefined && (
                            <div>
                              <div className="flex items-center justify-between mb-1">
                                <span className="text-xs text-muted-foreground">
                                  Output
                                </span>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="h-5 text-xs px-1"
                                  onClick={() => copyToClipboard(node.output)}
                                >
                                  <Copy size={10} />
                                </Button>
                              </div>
                              <pre className="p-2 rounded-md bg-muted/30 text-xs overflow-x-auto whitespace-pre-wrap font-mono max-h-40 overflow-y-auto">
                                {typeof node.output === "string"
                                  ? node.output
                                  : JSON.stringify(node.output, null, 2)}
                              </pre>
                            </div>
                          )}
                          {node.error && (
                            <div>
                              <span className="text-xs text-red-500">Error</span>
                              <pre className="p-2 rounded-md bg-red-500/10 text-xs text-red-500 overflow-x-auto whitespace-pre-wrap font-mono">
                                {node.error}
                              </pre>
                            </div>
                          )}
                        </div>
                      </CollapsibleContent>
                    </Collapsible>
                  ))}
                </div>
              </div>
            )}

            {/* Inputs */}
            {inputs && Object.keys(inputs).length > 0 && (
              <div className="space-y-2">
                <h4 className="text-sm font-medium text-muted-foreground">
                  Inputs
                </h4>
                <pre className="p-3 rounded-md bg-muted/30 text-xs overflow-x-auto whitespace-pre-wrap font-mono">
                  {JSON.stringify(inputs, null, 2)}
                </pre>
              </div>
            )}

            {/* Metadata */}
            {(executionId || startedAt || completedAt) && (
              <div className="text-xs text-muted-foreground space-y-1 pt-4 border-t">
                {executionId && (
                  <div className="flex justify-between">
                    <span>Execution ID:</span>
                    <span className="font-mono text-right truncate max-w-[200px]" title={executionId}>
                      {executionId}
                    </span>
                  </div>
                )}
                {startedAt && (
                  <div className="flex justify-between">
                    <span>Started:</span>
                    <span>{new Date(startedAt).toLocaleString()}</span>
                  </div>
                )}
                {completedAt && (
                  <div className="flex justify-between">
                    <span>Completed:</span>
                    <span>{new Date(completedAt).toLocaleString()}</span>
                  </div>
                )}
              </div>
            )}
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
};

export default ExecutionResultModal;
