// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// Chat & Projects API - Conversations, messages, and project organization

import { fetchWithAuth, fetchStream, getTokens } from '../apiClient';
import type {
  Conversation,
  ChatMode,
  ChatMessage,
  Project,
  ProjectCreate,
  ProjectUpdate,
  StreamOptions,
} from '@/types/api';
import type { AgentStreamChunk } from '@/types/streaming';
import type { StreamChunk } from './common';

// Chat API request/response types
interface ConversationListResponse {
  conversations: Conversation[];
  total: number;
}

interface MessageListResponse {
  messages: ChatMessage[];
  total: number;
  has_more: boolean;
}

// Chat API - Real backend calls
export const chatApi = {
  getConversations: async (params?: {
    limit?: number;
    offset?: number;
    mode?: ChatMode;
    status?: 'active' | 'archived';
  }): Promise<{ conversations: Conversation[]; total: number; has_more: boolean }> => {
    const searchParams = new URLSearchParams();
    if (params?.limit) searchParams.set('limit', String(params.limit));
    if (params?.offset) searchParams.set('offset', String(params.offset));
    if (params?.mode) searchParams.set('mode', params.mode);
    if (params?.status) searchParams.set('status', params.status);
    const query = searchParams.toString();
    const response = await fetchWithAuth<ConversationListResponse>(
      `/chat/conversations${query ? `?${query}` : ''}`
    );
    return {
      conversations: response.conversations ?? [],
      total: response.total,
      has_more:
        (params?.offset ?? 0) +
          (response.conversations ? response.conversations.length : 0) <
        response.total,
    };
  },

  getConversation: async (id: string): Promise<Conversation> => {
    return fetchWithAuth<Conversation>(`/chat/conversations/${id}`);
  },

  getMessages: async (
    conversationId: string,
    params?: { limit?: number; offset?: number }
  ): Promise<{ messages: ChatMessage[]; total: number; has_more: boolean }> => {
    const searchParams = new URLSearchParams();
    if (params?.limit) searchParams.set('limit', String(params.limit));
    if (params?.offset) searchParams.set('offset', String(params.offset));
    const query = searchParams.toString();
    const response = await fetchWithAuth<MessageListResponse>(
      `/chat/history/${conversationId}${query ? `?${query}` : ''}`
    );
    return {
      messages: response.messages ?? [],
      total: response.total,
      has_more: response.has_more,
    };
  },

  createConversation: async (mode: ChatMode, title?: string): Promise<Conversation> => {
    return fetchWithAuth<Conversation>('/chat/conversations', {
      method: 'POST',
      body: JSON.stringify({ mode, title }),
    });
  },

  deleteConversation: async (id: string): Promise<void> => {
    return fetchWithAuth<void>(`/chat/conversations/${id}`, {
      method: 'DELETE',
    });
  },

  bulkDeleteConversations: async (ids: string[]): Promise<{
    deleted_count: number;
    failed_ids: string[];
    message: string;
  }> => {
    return fetchWithAuth<{
      deleted_count: number;
      failed_ids: string[];
      message: string;
    }>('/chat/conversations/bulk', {
      method: 'DELETE',
      body: JSON.stringify({ conversation_ids: ids }),
    });
  },

  deleteAllConversations: async (): Promise<{
    deleted_count: number;
    message: string;
  }> => {
    return fetchWithAuth<{
      deleted_count: number;
      message: string;
    }>('/chat/conversations/all', {
      method: 'DELETE',
    });
  },

  updateConversation: async (id: string, updates: { title?: string; mode?: ChatMode }): Promise<Conversation> => {
    return fetchWithAuth<Conversation>(`/chat/conversations/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(updates),
    });
  },

  addMessage: async (conversationId: string, content: string, role: 'user' | 'assistant' = 'user'): Promise<ChatMessage> => {
    return fetchWithAuth<ChatMessage>(`/chat/conversations/${conversationId}/messages`, {
      method: 'POST',
      body: JSON.stringify({ content, role }),
    });
  },

  sendMessage: async (
    conversationId: string,
    content: string,
    mode: ChatMode = 'chat'
  ): Promise<ChatMessage> => {
    // Non-streaming chat completion - calls POST /chat (not /chat/completions)
    const response = await fetchWithAuth<{
      response: string;
      conversation_id: string;
      tool_calls: Array<{ tool: string; args: Record<string, unknown>; result: string | null }>;
      exports: Record<string, unknown>;
      usage: { prompt_tokens: number; completion_tokens: number; total_tokens: number };
      mode: string;
    }>('/chat', {
      method: 'POST',
      body: JSON.stringify({
        message: content,
        mode,
        conversation_id: conversationId,
      }),
    });
    // Map backend ChatResponse to frontend ChatMessage
    return {
      id: conversationId, // Use conversation ID as message doesn't have separate ID
      role: 'assistant',
      content: response.response, // Backend uses 'response', frontend expects 'content'
      tool_calls: response.tool_calls?.map(tc => ({
        ...tc,
        status: 'complete' as const,
      })),
      cached: false, // Backend doesn't return cached status for non-streaming
      created_at: new Date().toISOString(),
      mode: (response.mode === 'chat' || response.mode === 'planner') ? response.mode : 'chat',
      usage: response.usage,
    };
  },

  shareConversation: async (
    conversationId: string,
    userId: string,
    permission: 'view' | 'edit'
  ): Promise<void> => {
    return fetchWithAuth<void>(`/chat/conversations/${conversationId}/share`, {
      method: 'PATCH',
      body: JSON.stringify({ user_id: userId, permission }),
    });
  },

  unshareConversation: async (conversationId: string, userId: string): Promise<void> => {
    return fetchWithAuth<void>(`/chat/conversations/${conversationId}/share/${userId}`, {
      method: 'DELETE',
    });
  },

  cancelOrchestration: async (conversationId: string): Promise<void> => {
    await fetchWithAuth<{ status: string; conversation_id: string }>(
      `/chat/${conversationId}/cancel`,
      { method: 'POST' }
    );
  },

  getStreamStatus: async (conversationId: string): Promise<{
    active: boolean;
    started_at?: number;
    mode?: string;
    accumulated_content?: string;
    accumulated_thinking?: string;
  }> => {
    return fetchWithAuth(`/chat/${conversationId}/stream-status`);
  },

  // GAP-020: SSE streaming chat via fetchStream with timing measurements
  // Supports optional AbortSignal for stop generation functionality
  streamMessage: async (
    conversationId: string,
    content: string,
    mode: ChatMode = 'chat',
    options: StreamOptions = {},
    onChunk: (chunk: StreamChunk) => void,
    signal?: AbortSignal
  ): Promise<void> => {
    const streamStart = performance.now();
    return fetchStream(
      '/chat/stream',
      {
        method: 'POST',
        body: JSON.stringify({
          message: content,
          mode,
          conversation_id: conversationId,
          enable_thinking: options.enable_thinking ?? false,
        }),
      },
      (data, timing) => {
        // Parse SSE data chunks and map backend events to frontend types
        try {
          const parsed = JSON.parse(data);

          // Backend sends two formats:
          // 1. Native Dryade format: {"type": "start|token|complete|error|stream_complete", ...}
          // 2. OpenAI-compatible format: {"object": "chat.completion.chunk", "choices": [...]}

          // Handle native Dryade format (has 'type' field)
          if (parsed.type === 'start') {
            console.log('SSE stream started:', parsed);
            return;
          }

          if (parsed.type === 'token') {
            const chunk: StreamChunk = {
              type: 'content',
              content: parsed.content || '',
              ttft: timing?.ttft,
              interval: timing?.interval
            };
            onChunk(chunk);
            return;
          }

          if (parsed.type === 'complete') {
            const chunk: StreamChunk = {
              type: 'complete',
              total_time: performance.now() - streamStart
            };
            onChunk(chunk);
            return;
          }

          if (parsed.type === 'error') {
            const chunk: StreamChunk = {
              type: 'error',
              message: parsed.message || 'Unknown error'
            };
            onChunk(chunk);
            return;
          }

          if (parsed.type === 'stream_complete') {
            console.log('SSE stream complete:', parsed);
            return;
          }

          // Handle OpenAI-compatible format (has 'object' field)
          if (parsed.object === 'chat.completion.chunk' && parsed.choices?.[0]) {
            const choice = parsed.choices[0];
            const delta = choice.delta || {};

            // Multi-Provider Thinking Support (Phase 75.1)
            // All providers normalize thinking to these formats:
            // 1. OpenAI-compatible: delta.reasoning_content (vLLM, DeepSeek)
            // 2. Dryade normalized: dryadeEvent.type === 'thinking' (Anthropic, OpenAI Responses, LiteLLM)
            // 3. Direct: parsed.type === 'thinking' (legacy/direct events)
            // The backend normalizes all provider-specific formats via emit_thinking() events.
            //
            // Handle reasoning_content as thinking (separate from regular content)
            // Process content BEFORE checking finish_reason to not lose final content
            if (delta.reasoning_content) {
              onChunk({
                type: 'thinking',
                agent: 'assistant',
                content: delta.reasoning_content,
                timestamp: new Date().toISOString(),
              } as AgentStreamChunk);
            }

            // Handle regular content (including final content in complete chunks)
            if (delta.content) {
              const chunk: StreamChunk = {
                type: 'content',
                content: delta.content,
                ttft: timing?.ttft,
                interval: timing?.interval
              };
              onChunk(chunk);
            }

            // Check for finish_reason AFTER processing content
            if (choice.finish_reason === 'stop') {
              const chunk: StreamChunk = {
                type: 'complete',
                total_time: performance.now() - streamStart
              };
              onChunk(chunk);
              return;
            }

            if (choice.finish_reason === 'error') {
              const chunk: StreamChunk = {
                type: 'error',
                message: parsed.error?.message || delta.content || 'Stream error'
              };
              onChunk(chunk);
              return;
            }

            // Handle Dryade-specific events embedded in OpenAI format
            // Backend flattens metadata to top level: {type, content, agent, ...}
            if (parsed.dryade) {
              const dryadeEvent = parsed.dryade;
              if (dryadeEvent.type === 'agent_start') {
                onChunk({
                  type: 'agent_start',
                  agent: dryadeEvent.agent || dryadeEvent.metadata?.agent || 'unknown',
                  task: dryadeEvent.task || dryadeEvent.metadata?.task,
                  timestamp: new Date().toISOString(),
                } as AgentStreamChunk);
              } else if (dryadeEvent.type === 'agent_complete') {
                onChunk({
                  type: 'agent_complete',
                  agent: dryadeEvent.agent || dryadeEvent.metadata?.agent || 'unknown',
                  result: dryadeEvent.result || dryadeEvent.metadata?.result,
                  timestamp: new Date().toISOString(),
                } as AgentStreamChunk);
              } else if (dryadeEvent.type === 'tool_start') {
                onChunk({
                  type: 'tool_start',
                  agent: dryadeEvent.agent || 'assistant',
                  tool: dryadeEvent.tool || dryadeEvent.metadata?.tool || 'unknown',
                  args: dryadeEvent.args || dryadeEvent.metadata?.args,
                  timestamp: new Date().toISOString(),
                } as AgentStreamChunk);
              } else if (dryadeEvent.type === 'tool_result') {
                onChunk({
                  type: 'tool_complete',
                  agent: dryadeEvent.agent || 'assistant',
                  tool: dryadeEvent.tool || dryadeEvent.metadata?.tool || 'unknown',
                  result: dryadeEvent.result || dryadeEvent.metadata?.result,
                  timestamp: new Date().toISOString(),
                } as AgentStreamChunk);
              } else if (dryadeEvent.type === 'thinking') {
                onChunk({
                  type: 'thinking',
                  agent: dryadeEvent.agent || 'assistant',
                  content: dryadeEvent.content || '',
                  timestamp: new Date().toISOString(),
                } as AgentStreamChunk);
              } else if (dryadeEvent.type === 'escalation') {
                // Orchestrator needs user decision (e.g., permission error)
                onChunk({
                  type: 'escalation',
                  content: dryadeEvent.content || 'How would you like to proceed?',
                  task_context: dryadeEvent.task_context,
                  inline: dryadeEvent.inline ?? true,
                  has_auto_fix: dryadeEvent.has_auto_fix ?? false,
                  timestamp: new Date().toISOString(),
                } as AgentStreamChunk);
              } else if (dryadeEvent.type === 'reasoning') {
                // Orchestrator reasoning visibility
                onChunk({
                  type: 'reasoning',
                  content: dryadeEvent.content || '',
                  detailed: dryadeEvent.detailed,
                  visibility: dryadeEvent.visibility || 'summary',
                  timestamp: new Date().toISOString(),
                } as AgentStreamChunk);
              }
            }
            return;
          }

          // Handle agent execution events (Phase 67)
          if (parsed.type === 'agent_start') {
            onChunk({
              type: 'agent_start',
              agent: parsed.agent,
              task: parsed.task,
              timestamp: parsed.timestamp,
            } as AgentStreamChunk);
            return;
          }

          if (parsed.type === 'agent_complete') {
            onChunk({
              type: 'agent_complete',
              agent: parsed.agent,
              result: parsed.result,
              error: parsed.error,
              timestamp: parsed.timestamp,
            } as AgentStreamChunk);
            return;
          }

          if (parsed.type === 'thinking') {
            onChunk({
              type: 'thinking',
              agent: parsed.agent,
              content: parsed.content,
              timestamp: parsed.timestamp,
            } as AgentStreamChunk);
            return;
          }

          if (parsed.type === 'tool_start') {
            onChunk({
              type: 'tool_start',
              agent: parsed.agent,
              tool: parsed.tool,
              args: parsed.args,
              timestamp: parsed.timestamp,
            } as AgentStreamChunk);
            return;
          }

          if (parsed.type === 'tool_complete') {
            onChunk({
              type: 'tool_complete',
              agent: parsed.agent,
              tool: parsed.tool,
              result: parsed.result,
              error: parsed.error,
              timestamp: parsed.timestamp,
            } as AgentStreamChunk);
            return;
          }

          // capability_request, capability_bound, capability_status handlers
          // removed - CapabilityNegotiator was deleted in Phase 80

          // Handle clarify events (human-in-the-loop)
          if (parsed.type === 'clarify') {
            onChunk({
              type: 'clarify',
              question: parsed.content || parsed.metadata?.question || '',
              options: parsed.metadata?.options || [],
              context: parsed.metadata?.context || {},
              timestamp: parsed.timestamp || new Date().toISOString(),
            } as AgentStreamChunk);
            return;
          }

          // Unknown format - log for debugging
          if (parsed.type === undefined && parsed.object === undefined) {
            console.warn('Unknown SSE event format:', parsed);
          }

        } catch {
          // If not JSON, treat as raw content (fallback)
          if (data !== '[DONE]') {
            onChunk({
              type: 'content',
              content: data,
              interval: timing?.interval
            });
          }
        }
      },
      signal // Pass abort signal to fetchStream
    );
  },
};

// Projects API - Organize conversations into projects
export const projectsApi = {
  async getProjects(includeArchived = false): Promise<{ projects: Project[]; total: number }> {
    const params = new URLSearchParams();
    if (includeArchived) params.set('include_archived', 'true');
    const query = params.toString();
    try {
      const response = await fetchWithAuth<{ projects: Project[]; total: number }>(
        `/projects${query ? `?${query}` : ''}`
      );
      return { projects: Array.isArray(response?.projects) ? response.projects : [], total: response?.total ?? 0 };
    } catch {
      return { projects: [], total: 0 };
    }
  },

  async createProject(data: ProjectCreate): Promise<Project> {
    return fetchWithAuth<Project>('/projects', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async getProject(id: string): Promise<Project> {
    return fetchWithAuth<Project>(`/projects/${id}`);
  },

  async updateProject(id: string, data: ProjectUpdate): Promise<Project> {
    return fetchWithAuth<Project>(`/projects/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  async deleteProject(id: string): Promise<void> {
    await fetchWithAuth<void>(`/projects/${id}`, {
      method: 'DELETE',
    });
  },

  async getProjectConversations(projectId: string): Promise<{ conversations: Conversation[]; total: number }> {
    return fetchWithAuth<{ conversations: Conversation[]; total: number }>(
      `/projects/${projectId}/conversations`
    );
  },

  async moveConversationToProject(conversationId: string, projectId: string | null): Promise<void> {
    await fetchWithAuth<void>(`/chat/conversations/${conversationId}/project`, {
      method: 'PATCH',
      body: JSON.stringify({ project_id: projectId }),
    });
  },

  async deleteProjectConversations(projectId: string): Promise<{
    deleted_count: number;
    message: string;
  }> {
    return fetchWithAuth<{
      deleted_count: number;
      message: string;
    }>(`/projects/${projectId}/conversations`, {
      method: 'DELETE',
    });
  },
};
