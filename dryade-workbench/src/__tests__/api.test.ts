// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { authApi, chatApi, workflowsApi } from '@/services/api';
import { server } from '@/mocks/server';
import { http, HttpResponse } from 'msw';

describe('API Service Contracts', () => {
  beforeEach(() => {
    // Clear localStorage before each test
    localStorage.clear();
  });

  describe('authApi', () => {
    it('should login and store tokens', async () => {
      // Mock login endpoint
      server.use(
        http.post('/api/auth/login', async () => {
          return HttpResponse.json({
            access_token: 'test_access_token',
            refresh_token: 'test_refresh_token',
            token_type: 'Bearer',
            expires_in: 3600,
          });
        })
      );

      const result = await authApi.login({
        email: 'testuser@example.com',
        password: 'testpass',
      });

      expect(result.access_token).toBe('test_access_token');
      expect(result.refresh_token).toBe('test_refresh_token');

      // Verify tokens are stored in localStorage
      const storedTokens = localStorage.getItem('auth_tokens');
      expect(storedTokens).not.toBeNull();
      const parsed = JSON.parse(storedTokens!);
      expect(parsed.access_token).toBe('test_access_token');
    });

    it('should register and store tokens', async () => {
      // Mock register endpoint
      server.use(
        http.post('/api/auth/register', async () => {
          return HttpResponse.json({
            access_token: 'new_access_token',
            refresh_token: 'new_refresh_token',
            token_type: 'Bearer',
            expires_in: 3600,
          });
        })
      );

      const result = await authApi.register({
        email: 'new@example.com',
        password: 'newpass',
        display_name: 'New User',
      });

      expect(result.access_token).toBe('new_access_token');

      // Verify tokens are stored
      const storedTokens = localStorage.getItem('auth_tokens');
      expect(storedTokens).not.toBeNull();
    });

    it('should refresh tokens', async () => {
      // Mock refresh endpoint
      server.use(
        http.post('/api/auth/refresh', async () => {
          return HttpResponse.json({
            access_token: 'refreshed_access_token',
            refresh_token: 'refreshed_refresh_token',
            token_type: 'Bearer',
            expires_in: 3600,
          });
        })
      );

      const result = await authApi.refresh('old_refresh_token');

      expect(result.access_token).toBe('refreshed_access_token');
      expect(result.refresh_token).toBe('refreshed_refresh_token');

      // Verify new tokens are stored
      const storedTokens = localStorage.getItem('auth_tokens');
      expect(storedTokens).not.toBeNull();
      const parsed = JSON.parse(storedTokens!);
      expect(parsed.access_token).toBe('refreshed_access_token');
    });

    it('should clear tokens on logout', async () => {
      // Store tokens first
      localStorage.setItem(
        'auth_tokens',
        JSON.stringify({
          access_token: 'test_token',
          refresh_token: 'test_refresh',
        })
      );

      // Mock logout endpoint
      server.use(
        http.post('/api/auth/logout', async () => {
          return HttpResponse.json({});
        })
      );

      await authApi.logout();

      // Verify tokens are cleared
      const storedTokens = localStorage.getItem('auth_tokens');
      expect(storedTokens).toBeNull();
    });
  });

  describe('chatApi', () => {
    beforeEach(() => {
      // Set auth tokens for authenticated requests
      localStorage.setItem(
        'auth_tokens',
        JSON.stringify({
          access_token: 'test_access_token',
          refresh_token: 'test_refresh_token',
        })
      );
    });

    it('should list conversations', async () => {
      // Mock conversations list endpoint
      server.use(
        http.get('/api/chat/conversations', async () => {
          return HttpResponse.json({
            conversations: [
              {
                id: 'conv-1',
                title: 'Test Conversation 1',
                mode: 'chat',
                created_at: '2024-01-01T00:00:00Z',
                updated_at: '2024-01-01T00:00:00Z',
              },
              {
                id: 'conv-2',
                title: 'Test Conversation 2',
                mode: 'agent',
                created_at: '2024-01-02T00:00:00Z',
                updated_at: '2024-01-02T00:00:00Z',
              },
            ],
            total: 2,
          });
        })
      );

      const result = await chatApi.getConversations();

      expect(result.conversations).toHaveLength(2);
      expect(result.conversations[0].id).toBe('conv-1');
      expect(result.conversations[1].mode).toBe('agent');
      expect(result.total).toBe(2);
      expect(result.has_more).toBe(false);
    });

    it('should send message and map response correctly', async () => {
      // Mock chat endpoint
      server.use(
        http.post('/api/chat', async () => {
          return HttpResponse.json({
            response: 'This is the assistant response',
            conversation_id: 'conv-123',
            tool_calls: [
              {
                tool: 'search',
                args: { query: 'test' },
                result: 'search results',
              },
            ],
            exports: {},
            usage: {
              prompt_tokens: 100,
              completion_tokens: 50,
              total_tokens: 150,
            },
            mode: 'chat',
          });
        })
      );

      const result = await chatApi.sendMessage('conv-123', 'Hello, assistant!');

      expect(result.role).toBe('assistant');
      expect(result.content).toBe('This is the assistant response');
      expect(result.tool_calls).toHaveLength(1);
      expect(result.tool_calls![0].tool).toBe('search');
      expect(result.usage?.total_tokens).toBe(150);
      expect(result.mode).toBe('chat');
    });

    it('should create conversation with correct parameters', async () => {
      server.use(
        http.post('/api/chat/conversations', async ({ request }) => {
          const body = (await request.json()) as { mode: string; title?: string };
          return HttpResponse.json({
            id: 'new-conv-id',
            title: body.title || 'New Conversation',
            mode: body.mode,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          });
        })
      );

      const result = await chatApi.createConversation('chat', 'My Chat');

      expect(result.id).toBe('new-conv-id');
      expect(result.title).toBe('My Chat');
      expect(result.mode).toBe('chat');
    });

    it('should get conversation messages with pagination', async () => {
      server.use(
        http.get('/api/chat/history/:id', async ({ params }) => {
          return HttpResponse.json({
            messages: [
              {
                id: 'msg-1',
                role: 'user',
                content: 'Hello',
                created_at: '2024-01-01T00:00:00Z',
              },
              {
                id: 'msg-2',
                role: 'assistant',
                content: 'Hi there!',
                created_at: '2024-01-01T00:00:01Z',
              },
            ],
            total: 2,
            has_more: false,
          });
        })
      );

      const result = await chatApi.getMessages('conv-123', {
        limit: 10,
        offset: 0,
      });

      expect(result.messages).toHaveLength(2);
      expect(result.messages[0].role).toBe('user');
      expect(result.messages[1].role).toBe('assistant');
      expect(result.total).toBe(2);
      expect(result.has_more).toBe(false);
    });
  });

  describe('workflowsApi', () => {
    beforeEach(() => {
      // Set auth tokens for authenticated requests
      localStorage.setItem(
        'auth_tokens',
        JSON.stringify({
          access_token: 'test_access_token',
          refresh_token: 'test_refresh_token',
        })
      );
    });

    it('should list workflows', async () => {
      server.use(
        http.get('/api/workflows', async () => {
          return HttpResponse.json({
            items: [
              {
                id: 1,
                name: 'Workflow 1',
                description: 'First workflow',
                status: 'active',
                is_public: true,
                created_at: '2024-01-01T00:00:00Z',
                updated_at: '2024-01-01T00:00:00Z',
              },
              {
                id: 2,
                name: 'Workflow 2',
                description: 'Second workflow',
                status: 'draft',
                is_public: false,
                created_at: '2024-01-02T00:00:00Z',
                updated_at: '2024-01-02T00:00:00Z',
              },
            ],
            total: 2,
          });
        })
      );

      const result = await workflowsApi.getWorkflows();

      expect(result.workflows).toHaveLength(2);
      expect(result.workflows[0].id).toBe(1);
      expect(result.workflows[0].name).toBe('Workflow 1');
      expect(result.workflows[1].status).toBe('draft');
      expect(result.total).toBe(2);
    });

    it('should get workflow with backend schema', async () => {
      server.use(
        http.get('/api/workflows/:id', async ({ params }) => {
          return HttpResponse.json({
            id: parseInt(params.id as string),
            name: 'Test Workflow',
            description: 'A test workflow',
            status: 'active',
            is_public: true,
            workflow_json: {
              nodes: [
                {
                  id: 'node-1',
                  type: 'start',
                  label: 'Start',
                  position: { x: 100, y: 100 },
                },
                {
                  id: 'node-2',
                  type: 'ai_processor',
                  label: 'AI Process',
                  position: { x: 300, y: 100 },
                  config: {
                    model: 'gpt-4',
                    prompt: 'Process this',
                  },
                },
              ],
              edges: [
                {
                  id: 'edge-1',
                  source: 'node-1',
                  target: 'node-2',
                },
              ],
              version: '1.0.0',
            },
            created_at: '2024-01-01T00:00:00Z',
            updated_at: '2024-01-01T00:00:00Z',
          });
        })
      );

      const result = await workflowsApi.getWorkflow(1);

      expect(result.id).toBe(1);
      expect(result.name).toBe('Test Workflow');
      expect(result.workflow_json.nodes).toHaveLength(2);
      expect(result.workflow_json.edges).toHaveLength(1);
      expect(result.workflow_json.nodes[0].type).toBe('start');
      // Note: WorkflowNodeBackend doesn't have config - check data instead
    });

    it('should create workflow with default nodes', async () => {
      server.use(
        http.post('/api/workflows', async ({ request }) => {
          const body = (await request.json()) as {
            name: string;
            description?: string;
            workflow_json?: unknown;
          };
          return HttpResponse.json({
            id: 99,
            name: body.name,
            description: body.description || '',
            status: 'draft',
            is_public: false,
            workflow_json: body.workflow_json || {
              nodes: [
                { id: 'start', type: 'start', label: 'Start', position: { x: 100, y: 200 } },
                { id: 'end', type: 'end', label: 'End', position: { x: 500, y: 200 } },
              ],
              edges: [],
              version: '1.0.0',
            },
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          });
        })
      );

      const result = await workflowsApi.createWorkflow({
        name: 'New Workflow',
        description: 'My new workflow',
      });

      expect(result.id).toBe(99);
      expect(result.name).toBe('New Workflow');
      expect(result.workflow_json.nodes).toHaveLength(2);
      expect(result.workflow_json.nodes[0].type).toBe('start');
      expect(result.workflow_json.nodes[1].type).toBe('end');
    });

    it('should execute workflow with inputs', async () => {
      server.use(
        http.post('/api/workflows/:id/execute', async ({ request }) => {
          const body = (await request.json()) as { inputs?: Record<string, unknown> };
          return HttpResponse.json({
            execution_id: 'exec-123',
            status: 'running',
          });
        })
      );

      const result = await workflowsApi.executeWorkflow(1, {
        input_text: 'test input',
        param1: 'value1',
      });

      // executeWorkflow returns void (SSE stream), no result to assert
      expect(result).toBeUndefined();
    });

    it('should filter workflows by status', async () => {
      server.use(
        http.get('/api/workflows', async ({ request }) => {
          const url = new URL(request.url);
          const status = url.searchParams.get('status');

          return HttpResponse.json({
            items: [
              {
                id: 1,
                name: 'Active Workflow',
                status: status || 'active',
                is_public: true,
                created_at: '2024-01-01T00:00:00Z',
                updated_at: '2024-01-01T00:00:00Z',
              },
            ],
            total: 1,
          });
        })
      );

      const result = await workflowsApi.getWorkflows({ status: 'active' });

      expect(result.workflows).toHaveLength(1);
      expect(result.workflows[0].status).toBe('active');
    });
  });
});
