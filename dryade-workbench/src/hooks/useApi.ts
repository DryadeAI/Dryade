// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// React Query Hooks Layer - Complete API integration hooks
// Based on COMPONENTS-API-4.md specification

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  authApi,
  usersApi,
  healthApi,
  chatApi,
  agentsApi,
  flowsApi,
  workflowsApi,
  // costsApi removed - migrated to plugin UI (plugins/cost_tracker/ui)
  queueApi,
  metricsApi,
  cacheApi,
  sandboxApi,
  healingApi,
  safetyApi,
  pluginsApi,
  // filesApi removed - migrated to plugin UI (plugins/file_safety/ui)
  extensionsApi,
  knowledgeApi,
  plansApi,
  // trainerApi removed - migrated to plugin UI (plugins/trainer/ui)
  modelsApi,
  EnterpriseLicenseRequiredError,
} from "@/services/api";
import type {
  LoginRequest,
  RegisterRequest,
  ChatMode,
  AgentFramework,
} from "@/types/api";

// ============== ERROR HANDLING UTILITIES ==============

/**
 * Get error message from various error types
 */
export const getApiErrorMessage = (error: unknown): string => {
  if (error instanceof Error) {
    return error.message;
  }
  if (typeof error === "object" && error !== null && "detail" in error) {
    return (error as { detail: string }).detail;
  }
  return "An unknown error occurred";
};

// ============== AUTH HOOKS ==============

export const useLogin = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (credentials: LoginRequest) => authApi.login(credentials),
    onSuccess: () => {
      // Tokens are stored by authApi.login() via setTokens()
      queryClient.invalidateQueries({ queryKey: ["user"] });
    },
  });
};

export const useRegister = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: RegisterRequest) => authApi.register(data),
    onSuccess: () => {
      // Tokens are stored by authApi.register() via setTokens()
      queryClient.invalidateQueries({ queryKey: ["user"] });
    },
  });
};

export const useLogout = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => authApi.logout(),
    onSuccess: () => {
      // Tokens are cleared by authApi.logout() via clearTokens()
      queryClient.clear();
    },
  });
};

export const useRefreshToken = () => {
  return useQuery({
    queryKey: ["auth", "refresh"],
    queryFn: () => {
      const tokensStr = localStorage.getItem("auth_tokens");
      const tokens = tokensStr ? JSON.parse(tokensStr) : null;
      const refreshToken = tokens?.refresh_token;
      if (!refreshToken) throw new Error("No refresh token");
      return authApi.refresh(refreshToken);
    },
    refetchInterval: 25 * 60 * 1000, // 25 minutes
    enabled: (() => {
      try {
        const tokensStr = localStorage.getItem("auth_tokens");
        const tokens = tokensStr ? JSON.parse(tokensStr) : null;
        return !!tokens?.refresh_token;
      } catch {
        return false;
      }
    })(),
    retry: false,
  });
};

export const useAdminSetup = () => {
  return useMutation({
    mutationFn: (data: RegisterRequest) => authApi.setupAdmin(data),
  });
};

export const useSSOLogin = () => {
  return useMutation({
    mutationFn: (provider: string) => authApi.initiateSSO(provider),
    onSuccess: (data) => {
      window.location.href = data.login_url;
    },
  });
};

// ============== USER HOOKS ==============

export const useCurrentUser = () => {
  return useQuery({
    queryKey: ["user", "me"],
    queryFn: () => usersApi.getCurrentUser(),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
};

export const useUpdateProfile = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (updates: Parameters<typeof usersApi.updateCurrentUser>[0]) =>
      usersApi.updateCurrentUser(updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["user", "me"] });
    },
  });
};

export const useUserSearch = (query: string) => {
  return useQuery({
    queryKey: ["users", "search", query],
    queryFn: () => usersApi.searchUsers(query),
    enabled: query.length >= 2,
  });
};

// ============== HEALTH HOOKS ==============

export const useHealth = () => {
  return useQuery({
    queryKey: ["health"],
    queryFn: () => healthApi.getHealth(),
    refetchInterval: 30000,
  });
};

export const useDetailedHealth = () => {
  return useQuery({
    queryKey: ["health", "detailed"],
    queryFn: () => healthApi.getDetailedHealth(),
  });
};

export const useHealthMetrics = () => {
  return useQuery({
    queryKey: ["health", "metrics"],
    queryFn: () => healthApi.getMetrics(),
    refetchInterval: 30000,
  });
};

// ============== CHAT HOOKS ==============

export const useConversations = (filters?: {
  status?: string;
  mode?: ChatMode;
  page?: number;
  limit?: number;
}) => {
  return useQuery({
    queryKey: ["conversations", filters],
    queryFn: () =>
      chatApi.getConversations({
        limit: filters?.limit || 20,
        offset: filters?.page ? (filters.page - 1) * (filters?.limit || 20) : 0,
        mode: filters?.mode,
        status: filters?.status as 'active' | 'archived' | undefined,
      }),
  });
};

// GAP-022: Single conversation fetch
export const useConversation = (id: string) => {
  return useQuery({
    queryKey: ["conversations", id],
    queryFn: () => chatApi.getConversation(id),
    enabled: !!id,
  });
};

export const useConversationMessages = (
  conversationId: string,
  params?: { limit?: number; offset?: number }
) => {
  return useQuery({
    queryKey: ["conversations", conversationId, "messages", params],
    queryFn: () => chatApi.getMessages(conversationId, params),
    enabled: !!conversationId,
  });
};

export const useCreateConversation = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ mode, title }: { mode: ChatMode; title?: string }) =>
      chatApi.createConversation(mode, title),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
    },
  });
};

// GAP-026: Delete conversation
export const useDeleteConversation = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => chatApi.deleteConversation(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
    },
  });
};

export const useSendMessage = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      conversationId,
      content,
      mode,
    }: {
      conversationId: string;
      content: string;
      mode?: ChatMode;
    }) => chatApi.sendMessage(conversationId, content, mode),
    onSuccess: (_, { conversationId }) => {
      queryClient.invalidateQueries({ queryKey: ["conversations", conversationId, "messages"] });
    },
  });
};

// GAP-028: Share conversation
export const useShareConversation = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      conversationId,
      userId,
      permission,
    }: {
      conversationId: string;
      userId: string;
      permission: 'view' | 'edit';
    }) => chatApi.shareConversation(conversationId, userId, permission),
    onSuccess: (_, { conversationId }) => {
      queryClient.invalidateQueries({ queryKey: ["conversations", conversationId] });
    },
  });
};

export const useUnshareConversation = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      conversationId,
      userId,
    }: {
      conversationId: string;
      userId: string;
    }) => chatApi.unshareConversation(conversationId, userId),
    onSuccess: (_, { conversationId }) => {
      queryClient.invalidateQueries({ queryKey: ["conversations", conversationId] });
    },
  });
};

// ============== AGENTS HOOKS ==============

export const useAgents = (params?: { framework?: AgentFramework; search?: string }) => {
  return useQuery({
    queryKey: ["agents", params],
    queryFn: () => agentsApi.getAgents(params),
  });
};

// GAP-029: Backend uses name as identifier (no separate id field)
export const useAgent = (name: string) => {
  return useQuery({
    queryKey: ["agents", name],
    queryFn: () => agentsApi.getAgent(name),
    enabled: !!name,
  });
};

export const useAgentTools = (agentName: string) => {
  return useQuery({
    queryKey: ["agents", agentName, "tools"],
    queryFn: () => agentsApi.getAgentTools(agentName),
    enabled: !!agentName,
  });
};

export const useExecuteAgent = () => {
  return useMutation({
    mutationFn: ({
      agentName,
      task,
      context,
    }: {
      agentName: string;
      task: string;
      context?: Record<string, unknown>;
    }) => agentsApi.invokeAgent(agentName, task, context),
  });
};

// GAP-034: POST /agents - Create new agent
export const useCreateAgent = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      name: string;
      description: string;
      framework: AgentFramework;
    }) => agentsApi.createAgent(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agents"] });
    },
  });
};

// GAP-034: DELETE /agents/{name} - Delete agent by name
export const useDeleteAgent = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => agentsApi.deleteAgent(name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agents"] });
    },
  });
};

// ============== FLOWS HOOKS ==============

export const useFlows = (params?: { status?: string }) => {
  return useQuery({
    queryKey: ["flows", params],
    queryFn: () => flowsApi.getFlows(params),
  });
};

export const useFlow = (id: string) => {
  return useQuery({
    queryKey: ["flows", id],
    queryFn: () => flowsApi.getFlow(id),
    enabled: !!id,
  });
};

export const useRunFlow = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, inputs }: { id: string; inputs?: Record<string, unknown> }) =>
      flowsApi.executeFlow(id, inputs),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["flows"] });
    },
  });
};

export const useStopFlow = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (executionId: string) => flowsApi.stopExecution(executionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["flows"] });
    },
  });
};

export const useFlowExecution = (executionId?: string) => {
  return useQuery({
    queryKey: ["flows", "execution", executionId],
    queryFn: () => flowsApi.getExecution(executionId!),
    enabled: !!executionId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "running" ? 2000 : false;
    },
  });
};

// ============== WORKFLOWS HOOKS ==============

export const useWorkflows = (params?: { status?: string; is_public?: boolean }) => {
  return useQuery({
    queryKey: ["workflows", params],
    queryFn: () => workflowsApi.getWorkflows(params),
  });
};

// Available for future use in workflow detail views and inline editing
export const useWorkflow = (id: number) => {
  return useQuery({
    queryKey: ["workflows", id],
    queryFn: () => workflowsApi.getWorkflow(id),
    enabled: id > 0,
  });
};

export const useCreateWorkflow = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: Parameters<typeof workflowsApi.createWorkflow>[0]) =>
      workflowsApi.createWorkflow(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
    },
  });
};

// Available for future use -- WorkflowPage currently uses workflowsApi.updateWorkflow directly
export const useSaveWorkflow = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: {
      id: number;
      data: Parameters<typeof workflowsApi.updateWorkflow>[1];
    }) => workflowsApi.updateWorkflow(id, data),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: ["workflows", id] });
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
    },
  });
};

export const useDeleteWorkflow = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => workflowsApi.deleteWorkflow(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
    },
  });
};

export const usePublishWorkflow = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => workflowsApi.publishWorkflow(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
    },
  });
};

// Available for future use -- workflow execution currently uses SSE via fetchStream
export const useExecuteWorkflow = () => {
  return useMutation({
    mutationFn: ({ id, inputs }: { id: number; inputs?: Record<string, unknown> }) =>
      workflowsApi.executeWorkflow(id, inputs),
  });
};

// Available for future use in workflow duplication UI
export const useCloneWorkflow = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, name }: { id: number; name?: string }) =>
      workflowsApi.cloneWorkflow(id, name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
    },
  });
};

export const useArchiveWorkflow = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => workflowsApi.archiveWorkflow(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
    },
  });
};

// ============== COSTS HOOKS (MIGRATED TO PLUGIN) ==============
// Costs hooks have been migrated to plugins/cost_tracker/ui
// The plugin UI bundle uses DryadeBridge for API calls
// See: plugins/cost_tracker/ui/src/lib/bridge-api.ts

// ============== QUEUE HOOKS ==============

export const useQueueStatus = () => {
  return useQuery({
    queryKey: ["queue", "status"],
    queryFn: () => queueApi.getStatus(),
    refetchInterval: 5000,
  });
};

// ============== METRICS HOOKS ==============

export const useLatencyMetrics = () => {
  return useQuery({
    queryKey: ["metrics", "latency"],
    queryFn: () => metricsApi.getLatency(),
  });
};

export const useLatencyRecent = (limit?: number) => {
  return useQuery({
    queryKey: ["metrics", "latency", "recent", limit],
    queryFn: () => metricsApi.getLatencyRecent(limit),
  });
};

export const useLatencyByMode = () => {
  return useQuery({
    queryKey: ["metrics", "latency", "by-mode"],
    queryFn: () => metricsApi.getLatencyByMode(),
  });
};

// ============== CACHE HOOKS ==============

export const useCacheStats = () => {
  return useQuery({
    queryKey: ["cache", "stats"],
    queryFn: () => cacheApi.getStats(),
  });
};

export const useCacheConfig = () => {
  return useQuery({
    queryKey: ["cache", "config"],
    queryFn: () => cacheApi.getConfig(),
  });
};

export const useUpdateCacheConfig = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (config: { enabled?: boolean; similarity_threshold?: number; ttl_seconds?: number }) =>
      cacheApi.updateConfig(config),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cache"] });
    },
  });
};

export const useClearCache = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => cacheApi.clear(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cache", "stats"] });
    },
  });
};

// ============== SANDBOX HOOKS ==============

export const useSandboxConfig = () => {
  return useQuery({
    queryKey: ["sandbox", "config"],
    queryFn: () => sandboxApi.getConfig(),
  });
};

export const useUpdateSandboxConfig = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (config: Parameters<typeof sandboxApi.updateConfig>[0]) =>
      sandboxApi.updateConfig(config),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sandbox"] });
    },
  });
};

export const useSandboxToolRegistry = () => {
  return useQuery({
    queryKey: ["sandbox", "tools"],
    queryFn: () => sandboxApi.getToolRegistry(),
  });
};

// ============== HEALING HOOKS ==============

export const useCircuitBreakers = () => {
  return useQuery({
    queryKey: ["healing", "circuit-breakers"],
    queryFn: () => healingApi.getCircuitBreakers(),
    refetchInterval: 10000,
  });
};

export const useResetCircuitBreaker = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => healingApi.resetCircuitBreaker(name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["healing", "circuit-breakers"] });
    },
  });
};

export const useRetryConfig = () => {
  return useQuery({
    queryKey: ["healing", "retry-config"],
    queryFn: () => healingApi.getRetryConfig(),
  });
};

// ============== SAFETY HOOKS ==============

export const useSafetyViolations = (params?: { severity?: string; limit?: number }) => {
  return useQuery({
    queryKey: ["safety", "violations", params],
    queryFn: () => safetyApi.getViolations(params),
  });
};

export const useSafetyStats = () => {
  return useQuery({
    queryKey: ["safety", "stats"],
    queryFn: () => safetyApi.getStats(),
  });
};

export const useSafetyConfig = () => {
  return useQuery({
    queryKey: ["safety", "config"],
    queryFn: () => safetyApi.getConfig(),
  });
};

// ============== PLUGINS HOOKS ==============

export const usePlugins = () => {
  return useQuery({
    queryKey: ["plugins"],
    queryFn: () => pluginsApi.getPlugins(),
  });
};

export const useTogglePlugin = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ name, enabled }: { name: string; enabled: boolean }) =>
      pluginsApi.togglePlugin(name, enabled),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["plugins"] });
    },
  });
};

export const usePluginConfig = (name: string) => {
  return useQuery({
    queryKey: ["plugins", name, "config"],
    queryFn: () => pluginsApi.getPluginConfig(name),
    enabled: !!name,
  });
};

export const useUpdatePluginConfig = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ name, config }: { name: string; config: Record<string, unknown> }) =>
      pluginsApi.updatePluginConfig(name, config),
    onSuccess: (_, { name }) => {
      queryClient.invalidateQueries({ queryKey: ["plugins", name, "config"] });
      queryClient.invalidateQueries({ queryKey: ["plugins", name, "configWithSchema"] });
    },
  });
};

export const usePluginConfigWithSchema = (name: string) => {
  return useQuery({
    queryKey: ["plugins", name, "configWithSchema"],
    queryFn: () => pluginsApi.getPluginConfigWithSchema(name),
    enabled: !!name,
  });
};

// ============== FILES HOOKS (MIGRATED TO PLUGIN) ==============
// Files hooks have been migrated to plugins/file_safety/ui
// The plugin UI bundle uses DryadeBridge for API calls
// See: plugins/file_safety/ui/src/lib/bridge-api.ts

// ============== KNOWLEDGE HOOKS ==============

export const useKnowledgeSources = () => {
  return useQuery({
    queryKey: ["knowledge", "sources"],
    queryFn: () => knowledgeApi.getSources(),
  });
};

export const useKnowledgeSource = (id: string) => {
  return useQuery({
    queryKey: ["knowledge", "sources", id],
    queryFn: () => knowledgeApi.getSource(id),
    enabled: !!id,
  });
};

// GAP-070: Updated to use options object for score_threshold
export const useKnowledgeSearch = (
  query: string,
  options?: {
    threshold?: number;
    source_ids?: string[];
    limit?: number;
  }
) => {
  return useQuery({
    queryKey: ["knowledge", "search", query, options],
    queryFn: () => knowledgeApi.search(query, {
      source_ids: options?.source_ids,
      threshold: options?.threshold ?? 0.7,
      limit: options?.limit,
    }),
    enabled: query.length >= 3,
  });
};

// GAP-069: Updated to use typed metadata for upload
export const useUploadDocument = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ file, metadata }: {
      file: File;
      metadata?: {
        crews?: string[];
        agents?: string[];
        name?: string;
        description?: string;
      };
    }) => knowledgeApi.uploadSource(file, metadata),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["knowledge", "sources"] });
    },
  });
};

export const useDeleteKnowledgeSource = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => knowledgeApi.deleteSource(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["knowledge", "sources"] });
    },
  });
};

export const useKnowledgeChunks = (sourceId: string) => {
  return useQuery({
    queryKey: ["knowledge", "sources", sourceId, "chunks"],
    queryFn: () => knowledgeApi.getChunks(sourceId),
    enabled: !!sourceId,
  });
};

export const useBindKnowledgeToAgent = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ sourceId, agentName }: { sourceId: string; agentName: string }) =>
      knowledgeApi.bindToAgent(sourceId, agentName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["knowledge", "sources"] });
    },
  });
};

// ============== PLANS HOOKS ==============

export const usePlans = (filters?: { status?: string; limit?: number }) => {
  return useQuery({
    queryKey: ["plans", filters],
    queryFn: () => plansApi.getPlans(filters),
  });
};

export const usePlan = (id: number) => {
  return useQuery({
    queryKey: ["plans", id],
    queryFn: () => plansApi.getPlan(id),
    enabled: id > 0,
  });
};

export const useCreatePlan = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: Parameters<typeof plansApi.createPlan>[0]) =>
      plansApi.createPlan(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["plans"] });
    },
  });
};

export const useUpdatePlan = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: {
      id: number;
      data: Parameters<typeof plansApi.updatePlan>[1];
    }) => plansApi.updatePlan(id, data),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: ["plans", id] });
      queryClient.invalidateQueries({ queryKey: ["plans"] });
    },
  });
};

export const useDeletePlan = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => plansApi.deletePlan(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["plans"] });
    },
  });
};

export const useApprovePlan = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => plansApi.approvePlan(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: ["plans", id] });
      queryClient.invalidateQueries({ queryKey: ["plans"] });
    },
  });
};

export const useExecutePlan = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => plansApi.executePlan(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["plans"] });
    },
  });
};

export const usePlanResults = (planId: number) => {
  return useQuery({
    queryKey: ["plans", planId, "results"],
    queryFn: () => plansApi.getResults(planId),
    enabled: planId > 0,
  });
};

export const useSubmitPlanFeedback = () => {
  return useMutation({
    mutationFn: ({
      planId,
      rating,
      comment,
    }: {
      planId: number;
      rating: number;
      comment?: string;
    }) => plansApi.submitFeedback(planId, rating, comment),
  });
};

export const usePlanTemplates = () => {
  return useQuery({
    queryKey: ["plan-templates"],
    queryFn: () => plansApi.getTemplates(),
  });
};

export const useInstantiateTemplate = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ name, params }: { name: string; params: Record<string, unknown> }) =>
      plansApi.instantiateTemplate(name, params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["plans"] });
    },
  });
};

// ============== TRAINER HOOKS (ENTERPRISE) ==============

// ============== TRAINER HOOKS (MIGRATED TO PLUGIN) ==============
// Trainer hooks have been migrated to plugins/trainer/ui
// The plugin UI bundle uses DryadeBridge for API calls
// See: plugins/trainer/ui/src/lib/bridge-api.ts

// ============== MODELS HOOKS (ENTERPRISE) ==============

export const useModels = () => {
  return useQuery({
    queryKey: ["trainer", "models"],
    queryFn: () => modelsApi.getModels(),
    retry: (failureCount, error) => {
      if (error instanceof EnterpriseLicenseRequiredError) return false;
      return failureCount < 3;
    },
  });
};

export const useModel = (id: string) => {
  return useQuery({
    queryKey: ["trainer", "models", id],
    queryFn: () => modelsApi.getModel(id),
    enabled: !!id,
  });
};

export const useSetDefaultModel = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => modelsApi.setDefault(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["trainer", "models"] });
    },
  });
};

export const useCreateModel = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: Parameters<typeof modelsApi.createModel>[0]) =>
      modelsApi.createModel(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["trainer", "models"] });
    },
  });
};

export const useDeleteModel = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => modelsApi.deleteModel(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["trainer", "models"] });
    },
  });
};

// GAP-089: Model comparison hook
export const useCompareModels = () => {
  return useMutation({
    mutationFn: (modelIds: string[]) => modelsApi.compareModels(modelIds),
  });
};

// GAP-089: Model metrics hook
export const useModelMetrics = (id: string) => {
  return useQuery({
    queryKey: ["trainer", "models", id, "metrics"],
    queryFn: () => modelsApi.getModelMetrics(id),
    enabled: !!id,
  });
};

// GAP-090: Routing options hook
export const useRoutingOptions = () => {
  return useQuery({
    queryKey: ["trainer", "routing", "options"],
    queryFn: () => modelsApi.getRoutingOptions(),
  });
};

// GAP-090: Classify for routing hook
export const useClassifyRouting = () => {
  return useMutation({
    mutationFn: (message: string) => modelsApi.classifyForRouting(message),
  });
};

// ============== EXTENSIONS HOOKS ==============

export const useExtensionStatus = () => {
  return useQuery({
    queryKey: ["extensions", "status"],
    queryFn: () => extensionsApi.getStatus(),
    refetchInterval: 30000,
  });
};

export const useExtensionMetrics = () => {
  return useQuery({
    queryKey: ["extensions", "metrics"],
    queryFn: () => extensionsApi.getMetrics(),
    refetchInterval: 30000,
  });
};

export const useExtensionTimeline = (params?: { limit?: number }) => {
  return useQuery({
    queryKey: ["extensions", "timeline", params],
    queryFn: () => extensionsApi.getTimeline(params),
  });
};

export const useExtensionConfig = () => {
  return useQuery({
    queryKey: ["extensions", "config"],
    queryFn: () => extensionsApi.getConfig(),
  });
};

// ============== PLUGINS ADDITIONAL HOOKS ==============

export const usePluginStatsSummary = () => {
  return useQuery({
    queryKey: ["plugins", "stats", "summary"],
    queryFn: () => pluginsApi.getStatsSummary(),
  });
};

export const usePlugin = (name: string) => {
  return useQuery({
    queryKey: ["plugins", name],
    queryFn: () => pluginsApi.getPlugin(name),
    enabled: !!name,
  });
};
