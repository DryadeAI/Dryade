// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useCallback, useRef, useEffect } from 'react';
import { fetchStream } from '@/services/apiClient';
import { executionsApi } from '@/services/api';
import type {
  ExecutionStatus,
  WorkflowSSEEvent,
} from '@/types/execution';

interface ExecutionNode {
  id: string;
  type: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  output?: string;
  error?: string;
}

interface ExecutionState {
  executionId: string | null;
  scenarioName: string | null;
  status: ExecutionStatus | 'idle';
  nodes: ExecutionNode[];
  currentNodeId: string | null;
  finalResult: unknown | null;
  error: string | null;
  startedAt: string | null;
  completedAt: string | null;
}

const initialState: ExecutionState = {
  executionId: null,
  scenarioName: null,
  status: 'idle',
  nodes: [],
  currentNodeId: null,
  finalResult: null,
  error: null,
  startedAt: null,
  completedAt: null,
};

export function useExecutionStream() {
  const [state, setState] = useState<ExecutionState>(initialState);
  const abortControllerRef = useRef<AbortController | null>(null);

  const handleEvent = useCallback((event: WorkflowSSEEvent) => {
    setState(prev => {
      switch (event.type) {
        case 'workflow_start':
          return {
            ...prev,
            executionId: event.execution_id,
            scenarioName: event.scenario_name,
            startedAt: event.timestamp,
            status: 'running',
          };

        case 'workflow_nodes':
          return {
            ...prev,
            nodes: event.nodes.map(n => ({
              id: n.id,
              type: n.type,
              status: 'pending' as const,
            })),
          };

        case 'node_complete': {
          const nodeIndex = prev.nodes.findIndex(n => n.id === event.node_id);
          if (nodeIndex === -1) return prev;

          const updatedNodes = [...prev.nodes];
          updatedNodes[nodeIndex] = {
            ...updatedNodes[nodeIndex],
            status: 'completed',
            output: typeof event.data === 'string'
              ? event.data
              : JSON.stringify(event.data, null, 2),
          };

          // Find next pending node to mark as running
          const nextPending = updatedNodes.find(n => n.status === 'pending');
          if (nextPending) {
            nextPending.status = 'running';
          }

          return {
            ...prev,
            nodes: updatedNodes,
            currentNodeId: nextPending?.id ?? null,
          };
        }

        case 'workflow_complete':
          return {
            ...prev,
            status: 'completed',
            finalResult: event.result,
            completedAt: event.timestamp,
            currentNodeId: null,
            nodes: prev.nodes.map(n => ({
              ...n,
              status: n.status === 'pending' ? 'completed' : n.status,
            })),
          };

        case 'error':
          return {
            ...prev,
            status: 'failed',
            error: event.error,
            completedAt: event.timestamp,
            currentNodeId: null,
          };

        default:
          return prev;
      }
    });
  }, []);

  const startExecution = useCallback(async (
    scenarioName: string,
    inputs: Record<string, unknown>
  ) => {
    // Abort any existing stream
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    // Reset state
    setState({
      ...initialState,
      status: 'running',
      scenarioName,
    });

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      await fetchStream(
        `/workflow-scenarios/${scenarioName}/trigger`,
        {
          method: 'POST',
          body: JSON.stringify(inputs),
          signal: controller.signal,
        },
        (chunk) => {
          // Parse SSE data - chunk comes without "data: " prefix from fetchStream
          try {
            const event = JSON.parse(chunk) as WorkflowSSEEvent;
            handleEvent(event);
          } catch {
            // Ignore parse errors for incomplete chunks
          }
        }
      );
    } catch (error) {
      if ((error as Error).name !== 'AbortError') {
        setState(prev => ({
          ...prev,
          status: 'failed',
          error: (error as Error).message,
          completedAt: new Date().toISOString(),
        }));
      }
    }
  }, [handleEvent]);

  const cancelExecution = useCallback(async () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    if (state.executionId) {
      try {
        await executionsApi.cancel(state.executionId);
      } catch {
        // Ignore cancel errors
      }
    }

    setState(prev => ({
      ...prev,
      status: 'cancelled',
      completedAt: new Date().toISOString(),
      currentNodeId: null,
    }));
  }, [state.executionId]);

  const reset = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    setState(initialState);
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  return {
    ...state,
    isRunning: state.status === 'running',
    isComplete: state.status === 'completed' || state.status === 'failed' || state.status === 'cancelled',
    startExecution,
    cancelExecution,
    reset,
  };
}
