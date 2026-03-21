// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// Flow Execution WebSocket Hook - Real-time flow execution monitoring
// Connects to backend /ws/flows/{execution_id} endpoint (GAP-034)

import { useState, useEffect, useRef, useCallback } from "react";
import type { FlowNodeStatus } from "@/types/api";

export type FlowWSStatus = "connected" | "connecting" | "reconnecting" | "disconnected" | "error";

interface NodeUpdate {
  nodeId: string;
  nodeName: string;
  status: FlowNodeStatus;
  output?: string;
  error?: string;
  durationMs?: number;
}

interface FlowProgress {
  executionId: string;
  status: "running" | "complete" | "error" | "cancelled";
  progress: number;
  currentNodeId?: string;
  nodes: NodeUpdate[];
  checkpoints: Array<{
    id: string;
    nodeId: string;
    nodeName: string;
    timestamp: string;
  }>;
}

interface LogEntry {
  timestamp: string;
  level: "info" | "warn" | "error" | "debug";
  message: string;
  nodeId?: string;
}

// Backend WebSocket message types (GAP-034)
interface FlowWSMessageProgress {
  type: "progress";
  execution_id: string;
  status: "running" | "complete" | "error" | "cancelled";
  progress_percent: number;
  current_node_id?: string;
}

interface FlowWSMessageNodeUpdate {
  type: "node_update";
  node_id: string;
  node_name: string;
  status: FlowNodeStatus;
  output?: string;
  error?: string;
  duration_ms?: number;
}

interface FlowWSMessageLog {
  type: "log";
  timestamp: string;
  level: "info" | "warn" | "error" | "debug";
  message: string;
  node_id?: string;
}

interface FlowWSMessageCheckpoint {
  type: "checkpoint";
  checkpoint_id: string;
  node_id: string;
  node_name: string;
  timestamp: string;
}

interface FlowWSMessageComplete {
  type: "complete";
  execution_id: string;
  status: "complete" | "error" | "cancelled";
  result?: unknown;
  error?: string;
}

interface FlowWSMessageError {
  type: "error";
  message: string;
}

type FlowWSMessage =
  | FlowWSMessageProgress
  | FlowWSMessageNodeUpdate
  | FlowWSMessageLog
  | FlowWSMessageCheckpoint
  | FlowWSMessageComplete
  | FlowWSMessageError;

interface UseFlowWebSocketOptions {
  executionId: string;
  token?: string;
  onProgress?: (progress: FlowProgress) => void;
  onNodeUpdate?: (update: NodeUpdate) => void;
  onLog?: (log: LogEntry) => void;
  onComplete?: (result: FlowProgress) => void;
  onError?: (error: string) => void;
  enabled?: boolean;
}

interface UseFlowWebSocketReturn {
  status: FlowWSStatus;
  progress: FlowProgress | null;
  logs: LogEntry[];
  reconnectAttempt: number;
  maxReconnects: number;
  cancel: () => void;
  reconnect: () => void;
  disconnect: () => void;
}

const MAX_RECONNECT_ATTEMPTS = 5;
const RECONNECT_INTERVAL = 3000;

// Build WebSocket URL from current location
const getWsUrl = (executionId: string, token?: string): string => {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const host = window.location.host;
  const baseUrl = `${protocol}//${host}/api/ws/flows/${executionId}`;

  // Add token as query param if provided (GAP-034: token auth for WS)
  if (token) {
    return `${baseUrl}?token=${encodeURIComponent(token)}`;
  }

  return baseUrl;
};

export const useFlowWebSocket = (options: UseFlowWebSocketOptions): UseFlowWebSocketReturn => {
  const {
    executionId,
    token,
    onProgress,
    onNodeUpdate,
    onLog,
    onComplete,
    onError,
    enabled = true,
  } = options;

  const [status, setStatus] = useState<FlowWSStatus>("disconnected");
  const [progress, setProgress] = useState<FlowProgress | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [reconnectAttempt, setReconnectAttempt] = useState(0);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const nodesMapRef = useRef<Map<string, NodeUpdate>>(new Map());

  const cleanup = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  const scheduleReconnect = useCallback(() => {
    if (reconnectAttempt < MAX_RECONNECT_ATTEMPTS) {
      setStatus("reconnecting");
      setReconnectAttempt((prev) => prev + 1);
      reconnectTimeoutRef.current = setTimeout(() => {
        connect();
      }, RECONNECT_INTERVAL);
    } else {
      setStatus("error");
      onError?.("Maximum reconnection attempts reached");
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reconnectAttempt, onError]);

  const connect = useCallback(() => {
    if (!enabled || !executionId) return;

    cleanup();
    setStatus("connecting");
    nodesMapRef.current.clear();

    try {
      const wsUrl = getWsUrl(executionId, token);
      wsRef.current = new WebSocket(wsUrl);

      wsRef.current.onopen = () => {
        setStatus("connected");
        setReconnectAttempt(0);

        // Initialize progress state
        const initialProgress: FlowProgress = {
          executionId,
          status: "running",
          progress: 0,
          nodes: [],
          checkpoints: [],
        };
        setProgress(initialProgress);
      };

      wsRef.current.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data) as FlowWSMessage;

          switch (message.type) {
            case "progress": {
              setProgress((prev) => {
                const updated: FlowProgress = {
                  executionId: message.execution_id,
                  status: message.status,
                  progress: message.progress_percent,
                  currentNodeId: message.current_node_id,
                  nodes: Array.from(nodesMapRef.current.values()),
                  checkpoints: prev?.checkpoints || [],
                };
                onProgress?.(updated);
                return updated;
              });
              break;
            }

            case "node_update": {
              const nodeUpdate: NodeUpdate = {
                nodeId: message.node_id,
                nodeName: message.node_name,
                status: message.status,
                output: message.output,
                error: message.error,
                durationMs: message.duration_ms,
              };

              nodesMapRef.current.set(message.node_id, nodeUpdate);
              onNodeUpdate?.(nodeUpdate);

              // Update progress with new node state
              setProgress((prev) => {
                if (!prev) return prev;
                return {
                  ...prev,
                  nodes: Array.from(nodesMapRef.current.values()),
                };
              });
              break;
            }

            case "log": {
              const logEntry: LogEntry = {
                timestamp: message.timestamp,
                level: message.level,
                message: message.message,
                nodeId: message.node_id,
              };
              setLogs((prev) => [...prev.slice(-99), logEntry]); // Keep last 100 logs
              onLog?.(logEntry);
              break;
            }

            case "checkpoint": {
              setProgress((prev) => {
                if (!prev) return prev;
                const checkpoint = {
                  id: message.checkpoint_id,
                  nodeId: message.node_id,
                  nodeName: message.node_name,
                  timestamp: message.timestamp,
                };
                return {
                  ...prev,
                  checkpoints: [...prev.checkpoints, checkpoint],
                };
              });
              break;
            }

            case "complete": {
              const finalProgress: FlowProgress = {
                executionId: message.execution_id,
                status: message.status,
                progress: 100,
                nodes: Array.from(nodesMapRef.current.values()),
                checkpoints: progress?.checkpoints || [],
              };
              setProgress(finalProgress);
              onProgress?.(finalProgress);
              onComplete?.(finalProgress);
              break;
            }

            case "error": {
              onError?.(message.message);
              break;
            }
          }
        } catch (err) {
          console.error("Failed to parse WebSocket message:", err);
        }
      };

      wsRef.current.onclose = (event) => {
        if (event.wasClean) {
          setStatus("disconnected");
        } else {
          // Connection was closed unexpectedly, try to reconnect
          scheduleReconnect();
        }
      };

      wsRef.current.onerror = (error) => {
        console.error("WebSocket error:", error);
        setStatus("error");
        onError?.("WebSocket connection error");
      };
    } catch (error) {
      console.error("Failed to create WebSocket:", error);
      setStatus("error");
      onError?.("Failed to connect");
    }
  }, [executionId, token, enabled, cleanup, onProgress, onNodeUpdate, onLog, onComplete, onError, progress?.checkpoints, scheduleReconnect]);

  const cancel = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      // Send cancel command to backend (GAP-101)
      wsRef.current.send(JSON.stringify({ type: "cancel" }));
    }
    cleanup();
    setStatus("disconnected");
    setProgress((prev) => prev ? { ...prev, status: "cancelled" } : null);
  }, [cleanup]);

  const disconnect = useCallback(() => {
    cleanup();
    setStatus("disconnected");
    setReconnectAttempt(0);
  }, [cleanup]);

  const reconnectManually = useCallback(() => {
    setReconnectAttempt(0);
    connect();
  }, [connect]);

  useEffect(() => {
    if (enabled && executionId) {
      connect();
    }
    return cleanup;
  }, [enabled, executionId, connect, cleanup]);

  return {
    status,
    progress,
    logs,
    reconnectAttempt,
    maxReconnects: MAX_RECONNECT_ATTEMPTS,
    cancel,
    reconnect: reconnectManually,
    disconnect,
  };
};

export default useFlowWebSocket;
