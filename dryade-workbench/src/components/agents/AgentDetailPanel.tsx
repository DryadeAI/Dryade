// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useEffect } from "react";
import { X, Loader2, AlertTriangle, RefreshCw, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import FrameworkBadge from "./FrameworkBadge";
import ToolAccordion from "./ToolAccordion";
import AgentExecutionForm from "./AgentExecutionForm";
import ExecutionResult, { ExecutionError } from "./ExecutionResult";
import { agentsApi } from "@/services/api";
import type { AgentDetail, AgentInvokeResponse } from "@/types/api";
import type { SetupStatus } from "@/services/api";

interface AgentDetailPanelProps {
  agentName: string;
  onClose: () => void;
}

type ViewState = "details" | "executing" | "result" | "error";

const AgentDetailPanel = ({ agentName, onClose }: AgentDetailPanelProps) => {
  const [agent, setAgent] = useState<AgentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [viewState, setViewState] = useState<ViewState>("details");
  const [isExecuting, setIsExecuting] = useState(false);
  const [executionResult, setExecutionResult] = useState<AgentInvokeResponse | null>(null);
  const [executionError, setExecutionError] = useState<string | null>(null);
  const [setupStatus, setSetupStatus] = useState<SetupStatus | null>(null);
  const [loadingSetup, setLoadingSetup] = useState(false);

  useEffect(() => {
    const loadAgent = async () => {
      setLoading(true);
      try {
        const data = await agentsApi.getAgent(agentName);
        setAgent(data);
      } catch (error) {
        console.error("Failed to load agent:", error);
      } finally {
        setLoading(false);
      }
    };
    loadAgent();
  }, [agentName]);

  // Check setup status when agent loads
  useEffect(() => {
    const checkSetup = async () => {
      if (!agent) return;
      setLoadingSetup(true);
      try {
        const status = await agentsApi.getAgentSetupStatus(agentName);
        setSetupStatus(status);
      } catch (error) {
        console.error("Failed to check setup status:", error);
        // Don't block on setup check failure
        setSetupStatus(null);
      } finally {
        setLoadingSetup(false);
      }
    };
    checkSetup();
  }, [agent, agentName]);

  const handleExecute = async (task: string, context?: Record<string, unknown>) => {
    setIsExecuting(true);
    setViewState("executing");
    try {
      const result = await agentsApi.invokeAgent(agentName, task, context);
      setExecutionResult(result);
      setViewState("result");
    } catch (error) {
      setExecutionError(error instanceof Error ? error.message : "Execution failed");
      setViewState("error");
    } finally {
      setIsExecuting(false);
    }
  };

  const handleReset = () => {
    setViewState("details");
    setExecutionResult(null);
    setExecutionError(null);
  };

  return (
    <div
      role="dialog"
      aria-labelledby="agent-detail-title"
      className="w-[400px] h-full border-l border-border bg-background flex flex-col"
    >
      {/* Header */}
      <div className="flex items-start justify-between p-4 border-b border-border">
        <div className="flex-1 min-w-0">
          {loading ? (
            <>
              <Skeleton className="h-6 w-32 mb-2" />
              <Skeleton className="h-4 w-20" />
            </>
          ) : agent ? (
            <>
              <h2 id="agent-detail-title" className="font-semibold text-lg truncate">
                {agent.name}
              </h2>
              <div className="flex items-center gap-2 mt-1">
                <FrameworkBadge framework={agent.framework} size="sm" />
                <span className="text-xs text-muted-foreground">v{agent.version}</span>
              </div>
            </>
          ) : null}
        </div>
        <Button variant="ghost" size="icon" onClick={onClose} className="shrink-0">
          <X size={18} />
        </Button>
      </div>

      {/* Content */}
      <ScrollArea className="flex-1">
        <div className="p-4 space-y-6">
          {loading ? (
            <div className="space-y-4">
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : agent ? (
            <>
              {/* Description */}
              <div>
                <p className="text-sm text-muted-foreground">{agent.description}</p>
                {agent.role && (
                  <p className="text-xs text-muted-foreground mt-2">
                    <span className="font-medium">Role:</span> {agent.role}
                  </p>
                )}
                {agent.goal && (
                  <p className="text-xs text-muted-foreground">
                    <span className="font-medium">Goal:</span> {agent.goal}
                  </p>
                )}
              </div>

              {/* Setup Status Banner */}
              {setupStatus && !setupStatus.ready && (
                <div className="p-3 rounded-lg bg-warning/10 border border-warning/30">
                  <div className="flex items-start gap-2">
                    <AlertTriangle size={16} className="text-warning shrink-0 mt-0.5" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-warning mb-1">
                        Setup incomplete
                      </p>
                      <p className="text-xs text-muted-foreground mb-2">
                        {setupStatus.missing.length} MCP server(s) not configured.
                        Agent may have limited functionality.
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {setupStatus.instructions.slice(0, 2).map((inst) => (
                          <Button
                            key={inst.server}
                            variant="outline"
                            size="sm"
                            className="h-7 text-xs"
                            onClick={() => {
                              if (inst.docs_url) {
                                window.open(inst.docs_url, '_blank');
                              }
                            }}
                          >
                            <ExternalLink size={12} className="mr-1" />
                            Setup {inst.name}
                          </Button>
                        ))}
                        {setupStatus.missing.length > 2 && (
                          <span className="text-xs text-muted-foreground self-center">
                            +{setupStatus.missing.length - 2} more
                          </span>
                        )}
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 shrink-0"
                      onClick={async () => {
                        setLoadingSetup(true);
                        try {
                          const status = await agentsApi.getAgentSetupStatus(agentName);
                          setSetupStatus(status);
                        } finally {
                          setLoadingSetup(false);
                        }
                      }}
                      disabled={loadingSetup}
                    >
                      <RefreshCw size={14} className={loadingSetup ? "animate-spin" : ""} />
                    </Button>
                  </div>
                </div>
              )}

              {/* Tools */}
              <div>
                <h3 className="text-sm font-medium mb-3">
                  Tools ({agent.tools.length})
                </h3>
                <ToolAccordion tools={agent.tools} />
              </div>

              {/* Execution Area */}
              <div className="pt-4 border-t border-border">
                {viewState === "details" && (
                  <Button 
                    onClick={() => setViewState("executing")} 
                    className="w-full"
                  >
                    Execute Task
                  </Button>
                )}

                {viewState === "executing" && (
                  <AgentExecutionForm
                    agentName={agent.name}
                    onExecute={handleExecute}
                    onCancel={handleReset}
                    isExecuting={isExecuting}
                  />
                )}

                {viewState === "result" && executionResult && (
                  <ExecutionResult
                    result={executionResult}
                    onExecuteAgain={handleReset}
                  />
                )}

                {viewState === "error" && executionError && (
                  <ExecutionError
                    error={executionError}
                    onRetry={handleReset}
                  />
                )}
              </div>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">Failed to load agent details.</p>
          )}
        </div>
      </ScrollArea>
    </div>
  );
};

export default AgentDetailPanel;
