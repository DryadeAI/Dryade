// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
/**
 * Container for agent execution streaming.
 * Manages multiple agent sections and dispatches events to the correct section.
 * Exports useThinkingStream hook for integration with ChatPage SSE handler.
 */
import { useState, useCallback, useMemo, useRef } from "react";
import { AgentSection, type AgentStatus } from "./AgentSection";
import type {
  AgentStreamChunk,
  ThinkingChunk,
  ToolStartChunk,
  ToolCompleteChunk,
} from "@/types/streaming";
import type { CapabilityStatus } from "./CapabilityBadge";

interface AgentState {
  status: AgentStatus;
  capabilityStatus: CapabilityStatus;
  capabilityDetails?: string;
  task?: string;
  content: string;
  toolCalls: ToolCallState[];
}

interface ToolCallState {
  tool: string;
  args?: Record<string, unknown>;
  result?: string;
  error?: string;
  imageContent?: Array<{ data: string; mimeType: string; alt_text?: string }>;
  status: "running" | "complete" | "error";
}

interface ThinkingStreamProps {
  className?: string;
  agents: Map<string, AgentState>;
}

/**
 * ThinkingStream component displays agent execution state.
 * Use useThinkingStream hook to get agents state and processChunk callback.
 */
export function ThinkingStream({ className, agents }: ThinkingStreamProps) {
  // Convert map to array for rendering, sorted by insertion order
  const agentList = useMemo(() => Array.from(agents.entries()), [agents]);

  return (
    <div className={className}>
      {agentList.length === 0 ? (
        <div className="text-sm text-muted-foreground italic p-4">
          No agent activity yet...
        </div>
      ) : (
        <div className="space-y-2">
          {agentList.map(([agentName, state]) => (
            <AgentSection
              key={agentName}
              agent={agentName}
              status={state.status}
              capabilityStatus={state.capabilityStatus}
              capabilityDetails={state.capabilityDetails}
              task={state.task}
            >
              {/* Thinking content as markdown */}
              {state.content && (
                <div className="prose prose-sm dark:prose-invert max-w-none">
                  <pre className="whitespace-pre-wrap text-sm font-mono">
                    {state.content}
                  </pre>
                </div>
              )}

              {/* Tool calls list */}
              {state.toolCalls.length > 0 && (
                <div className="mt-3 space-y-2">
                  <p className="text-xs font-medium text-muted-foreground">
                    Tool Calls
                  </p>
                  {state.toolCalls.map((tc, idx) => (
                    <details
                      key={`${tc.tool}-${idx}`}
                      className="text-xs bg-muted rounded overflow-hidden"
                      open={tc.status === "running"}
                    >
                      <summary className="flex items-center gap-2 p-2 cursor-pointer hover:bg-muted/80">
                        <span className="font-mono flex-1">{tc.tool}</span>
                        {tc.status === "running" && (
                          <span className="text-info animate-pulse">running...</span>
                        )}
                        {tc.status === "complete" && (
                          <span className="text-success">✓</span>
                        )}
                        {tc.status === "error" && (
                          <span className="text-destructive">✗</span>
                        )}
                      </summary>
                      <div className="px-2 pb-2 space-y-1">
                        {tc.args && Object.keys(tc.args).length > 0 && (
                          <pre className="text-[10px] text-muted-foreground whitespace-pre-wrap font-mono bg-background/50 rounded p-1.5 max-h-20 overflow-auto">
                            {JSON.stringify(tc.args, null, 2)}
                          </pre>
                        )}
                        {tc.result && (
                          <pre className="text-[10px] text-muted-foreground whitespace-pre-wrap font-mono bg-background/50 rounded p-1.5 max-h-32 overflow-auto">
                            {tc.result}
                          </pre>
                        )}
                        {tc.imageContent && tc.imageContent.length > 0 && (
                          <div className="flex flex-wrap gap-2 p-1.5">
                            {tc.imageContent.map((img, imgIdx) => (
                              <img
                                key={imgIdx}
                                src={`data:${img.mimeType};base64,${img.data}`}
                                alt={img.alt_text || `Generated image ${imgIdx + 1}`}
                                className="max-w-48 max-h-48 rounded border object-contain"
                              />
                            ))}
                          </div>
                        )}
                        {tc.error && (
                          <pre className="text-[10px] text-destructive whitespace-pre-wrap font-mono bg-destructive/5 rounded p-1.5 max-h-20 overflow-auto">
                            {tc.error}
                          </pre>
                        )}
                      </div>
                    </details>
                  ))}
                </div>
              )}
            </AgentSection>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Hook for managing ThinkingStream state.
 * Returns agents map and processChunk callback for SSE integration.
 *
 * Usage in ChatPage:
 * ```typescript
 * const { agents, processChunk } = useThinkingStream();
 *
 * // In SSE handler:
 * if (isAgentChunk(chunk)) {
 *   processChunk(chunk);
 * }
 *
 * // In render:
 * <ThinkingStream agents={agents} />
 * ```
 */
export function useThinkingStream() {
  const [agents, setAgents] = useState<Map<string, AgentState>>(new Map());
  const agentsRef = useRef(agents);
  agentsRef.current = agents;

  // Process incoming chunk and update state
  const processChunk = useCallback((chunk: AgentStreamChunk) => {
    setAgents((prev) => {
      const next = new Map(prev);

      switch (chunk.type) {
        case "agent_start": {
          const existing = next.get(chunk.agent);
          if (existing) {
            // Agent already exists - update task but preserve accumulated state
            next.set(chunk.agent, {
              ...existing,
              status: "running",
              task: chunk.task,
            });
          } else {
            // New agent - create fresh state
            next.set(chunk.agent, {
              status: "running",
              capabilityStatus: "full",
              task: chunk.task,
              content: "",
              toolCalls: [],
            });
          }
          break;
        }

        case "agent_complete": {
          const completeChunk = chunk as import("@/types/streaming").AgentCompleteChunk;
          const current = next.get(chunk.agent);
          if (current) {
            // Append result to content so it renders inside the foldable agent section
            let content = current.content;
            if (completeChunk.result) {
              const summary = completeChunk.result.length > 200
                ? completeChunk.result.slice(0, 200) + "..."
                : completeChunk.result;
              content = content
                ? content + "\n" + summary
                : summary;
            }
            next.set(chunk.agent, {
              ...current,
              content,
              status: completeChunk.error ? "error" : "complete",
            });
          }
          break;
        }

        case "thinking": {
          const thinkingChunk = chunk as ThinkingChunk;
          const current = next.get(thinkingChunk.agent);
          if (current) {
            next.set(thinkingChunk.agent, {
              ...current,
              content: current.content + thinkingChunk.content,
            });
          }
          break;
        }

        case "tool_start": {
          const toolStart = chunk as ToolStartChunk;
          const current = next.get(toolStart.agent);
          if (current) {
            next.set(toolStart.agent, {
              ...current,
              toolCalls: [
                ...current.toolCalls,
                {
                  tool: toolStart.tool,
                  args: toolStart.args,
                  status: "running",
                },
              ],
            });
          }
          break;
        }

        case "tool_complete": {
          const toolComplete = chunk as ToolCompleteChunk;
          const current = next.get(toolComplete.agent);
          if (current) {
            const newStatus: "complete" | "error" = toolComplete.error ? "error" : "complete";
            const toolCalls = current.toolCalls.map((tc) =>
              tc.tool === toolComplete.tool && tc.status === "running"
                ? {
                    ...tc,
                    result: toolComplete.result,
                    error: toolComplete.error,
                    imageContent: (toolComplete as Record<string, unknown>).image_content as ToolCallState["imageContent"],
                    status: newStatus,
                  }
                : tc
            );
            next.set(toolComplete.agent, { ...current, toolCalls });
          }
          break;
        }

        // capability_status case removed - CapabilityNegotiator was deleted in Phase 80
      }

      return next;
    });
  }, []);

  // Reset state (for new conversation)
  const reset = useCallback(() => {
    setAgents(new Map());
  }, []);

  return { agents, processChunk, reset };
}

export type { AgentState, ToolCallState, ThinkingStreamProps };
