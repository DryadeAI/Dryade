// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// Agents & Flows API - Agent management and flow orchestration

import { fetchWithAuth } from '../apiClient';
import type {
  Agent,
  AgentFramework,
  AgentDetail,
  AgentTool,
  AgentInvokeResponse,
  Flow,
  FlowDetail,
  FlowExecution,
  FlowStatus,
} from '@/types/api';

// Backend response types for Agents API (map to frontend Agent type)
interface AgentInfoResponse {
  name: string;
  description: string;
  framework: AgentFramework;
  tools: string[];
  version?: string;
  role?: string;
  goal?: string;
}

interface AgentInvokeBackendResponse {
  result: string;
  tool_calls: Array<{
    tool_name: string;
    arguments: Record<string, unknown>;
    result: string;
    duration_ms: number;
  }>;
  execution_time_ms: number;
  tokens_used?: number;
  cost?: number;
  usage?: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    cost: number;
  };
}

// Setup status types for agent MCP server configuration
export interface SetupInstruction {
  server: string;
  reason: string;
  name: string;
  description: string;
  package: string;
  env_vars: string[];
  setup_steps: string[];
  verification_command?: string;
  docs_url?: string;
}

export interface SetupStatus {
  ready: boolean;
  missing: { server: string; reason: string }[];
  setup_url?: string;
  instructions: SetupInstruction[];
}

// Agents API - Real backend calls
export const agentsApi = {
  getAgents: async (params?: {
    framework?: AgentFramework;
    search?: string;
  }): Promise<{ agents: Agent[]; total: number }> => {
    const searchParams = new URLSearchParams();
    if (params?.framework) searchParams.set('framework', params.framework);
    if (params?.search) searchParams.set('search', params.search);
    const query = searchParams.toString();

    const response = await fetchWithAuth<AgentInfoResponse[]>(
      `/agents${query ? `?${query}` : ''}`
    );

    // Defensive: ensure response is an array before mapping
    const data = Array.isArray(response) ? response : [];

    // Map backend AgentInfo to frontend Agent (GAP-029: use name as id)
    const agents: Agent[] = data.map((info) => ({
      id: info.name, // Use name as id since backend doesn't provide id
      name: info.name,
      description: info.description,
      framework: info.framework,
      tool_count: info.tools?.length ?? 0,
      version: info.version || '1.0.0',
      tags: [], // Frontend-only field, not from backend
      role: info.role,
      goal: info.goal,
    }));

    return { agents, total: agents.length };
  },

  getAgent: async (name: string): Promise<AgentDetail> => {
    const response = await fetchWithAuth<AgentInfoResponse>(`/agents/${name}`);

    // Fetch tools separately
    const toolsResponse = await fetchWithAuth<AgentTool[]>(
      `/agents/${name}/tools`
    );

    return {
      id: response.name,
      name: response.name,
      description: response.description,
      framework: response.framework,
      tool_count: response.tools.length,
      version: response.version || '1.0.0',
      tags: [],
      tools: toolsResponse,
      role: response.role,
      goal: response.goal,
    };
  },

  getAgentTools: async (name: string): Promise<{ tools: AgentTool[] }> => {
    // GAP-032: Backend returns flat array, not wrapped
    const tools = await fetchWithAuth<AgentTool[]>(`/agents/${name}/tools`);
    return { tools };
  },

  invokeAgent: async (
    agentName: string,
    task: string,
    context?: Record<string, unknown>
  ): Promise<AgentInvokeResponse> => {
    const response = await fetchWithAuth<AgentInvokeBackendResponse>(
      `/agents/${agentName}/invoke`,
      {
        method: 'POST',
        body: JSON.stringify({ task, context }),
      }
    );

    // Map backend response to frontend type (GAP-033: add tokens_used/cost)
    // Backend now returns flat tokens_used/cost fields, fallback to usage object for compatibility
    return {
      result: response.result,
      tool_calls: response.tool_calls.map((tc) => ({
        tool: tc.tool_name,
        args: tc.arguments,
        result: tc.result,
        duration_ms: tc.duration_ms,
      })),
      execution_time_ms: response.execution_time_ms,
      tokens_used: response.tokens_used ?? response.usage?.total_tokens ?? 0,
      cost: response.cost ?? response.usage?.cost ?? 0,
    };
  },

  createAgent: async (data: {
    name: string;
    description: string;
    framework: AgentFramework;
  }): Promise<Agent> => {
    const response = await fetchWithAuth<AgentInfoResponse>('/agents', {
      method: 'POST',
      body: JSON.stringify(data),
    });
    return {
      id: response.name,
      name: response.name,
      description: response.description,
      framework: response.framework,
      tool_count: response.tools.length,
      version: response.version || '1.0.0',
      tags: [],
      role: response.role,
      goal: response.goal,
    };
  },

  deleteAgent: async (name: string): Promise<void> => {
    return fetchWithAuth<void>(`/agents/${name}`, {
      method: 'DELETE',
    });
  },

  getAgentSetupStatus: async (name: string): Promise<SetupStatus> => {
    return fetchWithAuth<SetupStatus>(`/agents/${name}/setup`);
  },
};

// Backend response types for Flows API
interface FlowInfoResponse {
  name: string;
  description?: string;
  entry_point?: string;
  checkpoints?: boolean;
}

interface ExecutionStatusResponse {
  execution_id: string;
  flow_name: string;
  status: 'pending' | 'running' | 'complete' | 'error' | 'cancelled';
  started_at?: string;
  completed_at?: string;
  result?: unknown;
  error?: string;
}

// Flows API - Real backend calls
export const flowsApi = {
  getFlows: async (params?: { status?: string }): Promise<{ flows: Flow[]; total: number }> => {
    const searchParams = new URLSearchParams();
    if (params?.status && params.status !== 'all') {
      searchParams.set('status', params.status);
    }
    const query = searchParams.toString();

    const response = await fetchWithAuth<FlowInfoResponse[]>(
      `/flows${query ? `?${query}` : ''}`
    );

    // Map backend FlowInfo to frontend Flow (defensive)
    const data = Array.isArray(response) ? response : [];
    const flows: Flow[] = data.map((info) => ({
      id: info.name, // Use name as id
      name: info.name,
      description: info.description,
      status: 'idle' as FlowStatus, // Default, not from list endpoint
      node_count: 0, // Not provided by backend list
      entry_point: info.entry_point, // GAP-035
    }));

    return { flows, total: flows.length };
  },

  getFlow: async (name: string): Promise<FlowDetail> => {
    const response = await fetchWithAuth<FlowInfoResponse>(`/flows/${name}`);

    return {
      id: response.name,
      name: response.name,
      description: response.description,
      status: 'idle',
      node_count: 0,
      entry_point: response.entry_point,
      nodes: [], // Flow nodes come from execution, not static definition
      edges: [],
    };
  },

  executeFlow: async (
    name: string,
    inputs?: Record<string, unknown>
  ): Promise<FlowExecution> => {
    // GAP-030: Use /kickoff not /execute
    const response = await fetchWithAuth<ExecutionStatusResponse>(
      `/flows/${name}/kickoff`,
      {
        method: 'POST',
        body: JSON.stringify({ inputs }),
      }
    );

    // Map to frontend FlowExecution (GAP-031)
    return {
      id: response.execution_id,
      flow_name: response.flow_name,
      status: response.status === 'complete' ? 'complete' :
              response.status === 'error' ? 'error' :
              response.status === 'cancelled' ? 'cancelled' : 'running',
      started_at: response.started_at || new Date().toISOString(),
      completed_at: response.completed_at,
      node_results: [], // Populated via WebSocket
      checkpoints: [],
    };
  },

  getExecution: async (executionId: string): Promise<FlowExecution> => {
    const response = await fetchWithAuth<ExecutionStatusResponse>(
      `/flows/executions/${executionId}`
    );

    return {
      id: response.execution_id,
      flow_name: response.flow_name,
      status: response.status === 'complete' ? 'complete' :
              response.status === 'error' ? 'error' :
              response.status === 'cancelled' ? 'cancelled' : 'running',
      started_at: response.started_at || '',
      completed_at: response.completed_at,
      node_results: [],
      checkpoints: [],
    };
  },

  stopExecution: async (executionId: string): Promise<void> => {
    // GAP-101: Send cancel to backend
    return fetchWithAuth<void>(`/flows/executions/${executionId}/cancel`, {
      method: 'POST',
    });
  },

  createFlow: async (data: {
    name: string;
    description?: string;
  }): Promise<Flow> => {
    // GAP-039: POST flow endpoint
    const response = await fetchWithAuth<FlowInfoResponse>('/flows', {
      method: 'POST',
      body: JSON.stringify(data),
    });

    return {
      id: response.name,
      name: response.name,
      description: response.description,
      status: 'idle',
      node_count: 0,
    };
  },

  resumeFromCheckpoint: async (
    executionId: string,
    checkpointId: string,
    inputs?: Record<string, unknown>
  ): Promise<FlowExecution> => {
    // GAP-037: Checkpoint handling
    const response = await fetchWithAuth<ExecutionStatusResponse>(
      `/flows/executions/${executionId}/resume`,
      {
        method: 'POST',
        body: JSON.stringify({ checkpoint_id: checkpointId, inputs }),
      }
    );

    return {
      id: response.execution_id,
      flow_name: response.flow_name,
      status: 'running',
      started_at: response.started_at || new Date().toISOString(),
      node_results: [],
      checkpoints: [],
    };
  },
};
