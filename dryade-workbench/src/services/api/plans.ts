// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// Plans API - Plan management, generation, execution

import { fetchWithAuth } from '../apiClient';
import type {
  Plan,
  PlanNode,
  PlanNodeStatus,
  PlanExecutionStart,
  PlanExecution,
} from '@/types/extended-api';

// Backend plan types for mapping
interface PlanBackendResponse {
  id: number;
  name: string;
  description?: string;
  status: 'draft' | 'approved' | 'executing' | 'completed' | 'failed' | 'cancelled';
  confidence?: number;
  estimated_cost?: number;
  reasoning?: string;
  conversation_id?: string;
  user_id?: string;
  created_at: string;
  updated_at: string;
  approved_at?: string;
  completed_at?: string;
  ai_generated: boolean;  // Phase 70-06: AI-generated flag
  plan_json: {
    nodes: PlanNodeBackend[];
    edges: PlanEdgeBackend[];
  };
}

interface PlanNodeBackend {
  id: string;
  type?: 'start' | 'task' | 'router' | 'end';  // Optional - DB format may not have type
  label?: string;  // Optional - DB format uses agent string instead
  description?: string;
  task?: string;  // DB format uses task instead of description
  agent?: string | { name: string; task: string };  // Can be string (DB) or object (workflow)
  tool?: string;  // MCP tool name
  arguments?: Record<string, unknown>;  // Tool arguments (JSON)
  dependencies?: string[];  // Workflow format
  depends_on?: string[];  // DB format
}

interface PlanEdgeBackend {
  id?: string;  // Optional - DB format may not have id
  source?: string;  // Workflow format
  target?: string;  // Workflow format
  from?: string;  // DB format
  to?: string;  // DB format
  condition?: string;
}

interface PlanExecutionResultBackendResponse {
  id: number;
  execution_id: string;
  plan_id: number;
  status: PlanExecution['status'];
  start_time?: string;
  end_time?: string;
  duration_ms?: number;
  total_cost?: number;
  node_results?: PlanExecution['node_results'] | null;
  user_feedback_rating?: number;
  user_feedback_comment?: string;
  created_at?: string;
}

// Phase 71.2: Backend response for plan generation (can be plan or clarification request)
interface GeneratePlanBackendResponse {
  type: 'plan' | 'clarification';
  plan?: PlanBackendResponse;
  questions?: string[];
  context?: string;
}

// Phase 71.2: Frontend response type for generatePlan
export interface GeneratePlanResponse {
  type: 'plan' | 'clarification';
  plan?: Plan;
  questions?: string[];
  context?: string;
}

// Plans API - Real backend calls (GAP-051, GAP-052, GAP-053, GAP-054, GAP-055, GAP-056)
export const plansApi = {
  getPlans: async (params?: {
    status?: string;
    limit?: number;
    offset?: number;
    ai_generated?: boolean;  // Phase 70-06: Filter by AI-generated
    conversation_id?: string;  // Filter by conversation
  }): Promise<{ plans: Plan[]; total: number }> => {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set('status', params.status);
    if (params?.limit) searchParams.set('limit', String(params.limit));
    if (params?.offset) searchParams.set('offset', String(params.offset));
    if (params?.ai_generated !== undefined) searchParams.set('ai_generated', String(params.ai_generated));
    if (params?.conversation_id) searchParams.set('conversation_id', params.conversation_id);
    const query = searchParams.toString();

    let response: { items: PlanBackendResponse[]; total: number };
    try {
      response = await fetchWithAuth<{ items: PlanBackendResponse[]; total: number }>(
        `/plans${query ? `?${query}` : ''}`
      );
    } catch {
      return { plans: [], total: 0 };
    }

    const items = Array.isArray(response?.items) ? response.items : [];

    // Map to frontend Plan type
    // Handle both planner format (agent as string, task) and workflow format (agent as object, description)
    const plans: Plan[] = items.map((p) => ({
      id: p.id,
      name: p.name,
      description: p.description,
      status: p.status,
      confidence: p.confidence,
      estimated_cost: p.estimated_cost,
      reasoning: p.reasoning,
      conversation_id: p.conversation_id,
      user_id: p.user_id,
      nodes: (p.plan_json?.nodes ?? []).map((n) => ({
        id: n.id,
        type: (n.type || 'task') as PlanNode['type'],
        label: n.label || (typeof n.agent === 'string' ? n.agent : n.agent?.name) || n.id,
        description: n.description || n.task,
        agent: typeof n.agent === 'string' ? n.agent : n.agent?.name,
        tool: n.tool,
        arguments: n.arguments,
        status: 'pending' as PlanNodeStatus,
        dependencies: n.dependencies || n.depends_on || [],
      })),
      // Normalize edges: backend may return {from, to} or {source, target}
      edges: (p.plan_json?.edges ?? []).map((e) => ({
        id: e.id || `edge-${e.from || e.source}-${e.to || e.target}`,
        source: e.source || e.from,
        target: e.target || e.to,
      })),
      created_at: p.created_at,
      updated_at: p.updated_at,
      approved_at: p.approved_at,
      completed_at: p.completed_at,
      ai_generated: p.ai_generated ?? false,  // Phase 70-06
    }));

    return { plans, total: response?.total ?? 0 };
  },

  getPlan: async (id: number): Promise<Plan> => {
    const response = await fetchWithAuth<PlanBackendResponse>(`/plans/${id}`);

    return {
      id: response.id,
      name: response.name,
      description: response.description,
      status: response.status,
      confidence: response.confidence,
      estimated_cost: response.estimated_cost,
      reasoning: response.reasoning,
      conversation_id: response.conversation_id,
      user_id: response.user_id,
      // Handle both planner format (agent as string, task) and workflow format (agent as object, description)
      nodes: response.plan_json.nodes.map((n): PlanNode => ({
        id: n.id,
        type: (n.type || 'task') as PlanNode['type'],
        label: String(typeof n.label === 'object' ? (n.label as { name?: string })?.name || n.agent : (n.label || n.agent || '')),
        description: n.description || n.task,
        agent: typeof n.agent === 'string' ? n.agent : n.agent?.name,
        tool: n.tool,
        arguments: n.arguments,
        status: 'pending' as PlanNodeStatus,
        dependencies: n.dependencies || n.depends_on || [],
      })),
      // Normalize edges: backend may return {from, to} or {source, target}
      edges: response.plan_json.edges.map((e) => ({
        id: e.id || `edge-${e.from || e.source}-${e.to || e.target}`,
        source: e.source || e.from,
        target: e.target || e.to,
      })),
      created_at: response.created_at,
      updated_at: response.updated_at,
      approved_at: response.approved_at,
      completed_at: response.completed_at,
      ai_generated: response.ai_generated ?? false,  // Phase 70-06
    };
  },

  // GAP-052: POST /plans
  // Backend expects nodes/edges as top-level fields, not nested in plan_json
  createPlan: async (data: {
    name: string;
    description?: string;
    conversation_id?: string;
    nodes: Array<{
      id: string;
      agent: string;
      task: string;
      depends_on?: string[];
    }>;
    edges?: Array<{ id?: string; from: string; to: string }>;
    confidence?: number;
    ai_generated?: boolean;
  }): Promise<Plan> => {
    const response = await fetchWithAuth<PlanBackendResponse>('/plans', {
      method: 'POST',
      body: JSON.stringify(data),
    });
    return plansApi.getPlan(response.id);
  },

  // GAP-052 FIXED: Backend expects PUT for updates
  // Backend expects nodes/edges as top-level fields, not nested in plan_json
  updatePlan: async (
    id: number,
    data: Partial<{
      name: string;
      description: string;
      nodes: Array<Record<string, unknown>>;
      edges: Array<Record<string, unknown>>;
      reasoning: string;
      confidence: number;
      status: Plan['status'];
    }>
  ): Promise<Plan> => {
    const response = await fetchWithAuth<PlanBackendResponse>(`/plans/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
    return plansApi.getPlan(response.id);
  },

  // GAP-052: DELETE /plans/{id}
  deletePlan: async (id: number): Promise<void> => {
    return fetchWithAuth<void>(`/plans/${id}`, {
      method: 'DELETE',
    });
  },

  // GAP-051: Approval workflow - approve then execute
  // FIXED: Backend only has PUT endpoint, not PATCH for partial updates
  approvePlan: async (id: number): Promise<Plan> => {
    const response = await fetchWithAuth<PlanBackendResponse>(`/plans/${id}`, {
      method: 'PUT',
      body: JSON.stringify({ status: 'approved' }),
    });
    return plansApi.getPlan(response.id);
  },

  cancelPlan: async (id: number): Promise<Plan> => {
    const response = await fetchWithAuth<PlanBackendResponse>(`/plans/${id}`, {
      method: 'PUT',
      body: JSON.stringify({ status: 'cancelled' }),
    });
    return plansApi.getPlan(response.id);
  },

  resetStuckPlan: async (id: number): Promise<{ message: string; plan_id: number; status: string; executions_reset: number }> => {
    return fetchWithAuth(`/plans/${id}/reset`, {
      method: 'POST',
      body: JSON.stringify({}),
    });
  },

  resetAllStuckPlans: async (): Promise<{ message: string; plans_reset: number; executions_reset: number; plan_ids: number[] }> => {
    return fetchWithAuth(`/plans/reset-stuck`, {
      method: 'POST',
      body: JSON.stringify({}),
    });
  },

  validatePlan: async (id: number): Promise<{
    valid: boolean;
    errors: string[];
    warnings: string[];
    node_issues: Array<{ node_id: string; agent: string; issues: string[] }>;
  }> => {
    return fetchWithAuth(`/plans/${id}/validate`, {
      method: 'POST',
      body: JSON.stringify({}),
    });
  },

  executePlan: async (id: number): Promise<PlanExecutionStart> => {
    return fetchWithAuth<PlanExecutionStart>(`/plans/${id}/execute`, {
      method: 'POST',
      body: JSON.stringify({}),
    });
  },

  getResults: async (id: number): Promise<PlanExecution[]> => {
    const response = await fetchWithAuth<PlanExecutionResultBackendResponse[]>(
      `/plans/${id}/executions`
    );

    return (Array.isArray(response) ? response : []).map((r) => ({
      id: r.execution_id,
      plan_id: r.plan_id,
      status: r.status,
      started_at: r.start_time || new Date().toISOString(),
      completed_at: r.end_time,
      duration_ms: r.duration_ms,
      total_cost: r.total_cost,
      user_feedback_rating: r.user_feedback_rating,
      user_feedback_comment: r.user_feedback_comment,
      created_at: r.created_at,
      node_results: r.node_results ?? [],
    }));
  },

  submitFeedback: async (
    planId: number,
    rating: number,
    comment?: string
  ): Promise<void> => {
    return fetchWithAuth<void>(`/plans/${planId}/feedback`, {
      method: 'POST',
      body: JSON.stringify({ rating, comment }),
    });
  },

  // GAP-056: Plan templates
  getTemplates: async (): Promise<{
    templates: Array<{ name: string; description: string; category: string }>;
  }> => {
    return fetchWithAuth<{
      templates: Array<{ name: string; description: string; category: string }>;
    }>('/plan-templates');
  },

  // Phase 70-03: Generate plan from natural language prompt
  // Phase 70-04: Added planId parameter for conversational refinement
  // Phase 71.2: Returns GeneratePlanResponse which may be plan or clarification request
  generatePlan: async (
    prompt: string,
    conversationId?: string,
    planId?: number  // For refinement - pass existing plan ID
  ): Promise<GeneratePlanResponse> => {
    const response = await fetchWithAuth<GeneratePlanBackendResponse>('/plans/generate', {
      method: 'POST',
      body: JSON.stringify({
        prompt,
        conversation_id: conversationId,
        plan_id: planId,  // Backend will refine this plan instead of creating new
      }),
    });

    // Phase 71.2: Handle clarification response
    if (response.type === 'clarification') {
      return {
        type: 'clarification',
        questions: response.questions || [],
        context: response.context || '',
      };
    }

    // Handle plan response
    const planData = response.plan!;
    return {
      type: 'plan',
      plan: {
        id: planData.id,
        name: planData.name,
        description: planData.description,
        status: planData.status,
        confidence: planData.confidence,
        estimated_cost: planData.estimated_cost,
        reasoning: planData.reasoning,
        conversation_id: planData.conversation_id,
        user_id: planData.user_id,
        // Handle both planner format (agent as string, task) and workflow format (agent as object, description)
        nodes: planData.plan_json.nodes.map((n): PlanNode => ({
          id: n.id,
          type: (n.type || 'task') as PlanNode['type'],
          label: String(typeof n.label === 'object' ? (n.label as { name?: string })?.name || n.agent : (n.label || n.agent || '')),
          description: n.description || n.task,
          agent: typeof n.agent === 'string' ? n.agent : n.agent?.name,
          status: 'pending' as PlanNodeStatus,
          dependencies: n.dependencies || n.depends_on || [],
        })),
        // Normalize edges: backend may return {from, to} or {source, target}
        edges: planData.plan_json.edges.map((e) => ({
          id: e.id || `edge-${e.from || e.source}-${e.to || e.target}`,
          source: e.source || e.from,
          target: e.target || e.to,
        })),
        created_at: planData.created_at,
        updated_at: planData.updated_at,
        approved_at: planData.approved_at,
        completed_at: planData.completed_at,
        ai_generated: planData.ai_generated ?? true,  // Phase 70-06: generated plans are AI-generated
      },
    };
  },

  instantiateTemplate: async (
    templateName: string,
    params: Record<string, unknown>
  ): Promise<Plan> => {
    const response = await fetchWithAuth<PlanBackendResponse>(
      `/plan-templates/${templateName}/instantiate`,
      {
        method: 'POST',
        body: JSON.stringify(params),
      }
    );
    return plansApi.getPlan(response.id);
  },
};
