// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { TooltipProvider } from '@/components/ui/tooltip';
import { http, HttpResponse } from 'msw';
import { server } from '@/mocks/server';
import ChatPage from '@/pages/ChatPage';
import EmptyState, { chatSuggestions } from '@/components/shared/EmptyState';

// Mock hooks that make external connections
vi.mock('@/hooks/useChatWebSocket', () => ({
  useChatWebSocket: () => ({
    status: 'disconnected',
    latencyMs: null,
    reconnectAttempt: 0,
    maxReconnects: 5,
    sendMessage: vi.fn(),
    cancelStream: vi.fn(),
    reconnect: vi.fn(),
  }),
}));

vi.mock('@/hooks/useExecutionStream', () => ({
  useExecutionStream: () => ({
    status: 'idle',
    nodes: [],
    currentNodeId: null,
    startedAt: null,
    completedAt: null,
    error: null,
    isComplete: false,
    scenarioName: null,
    executionId: null,
    finalResult: null,
    startExecution: vi.fn(),
    cancelExecution: vi.fn(),
    reset: vi.fn(),
  }),
}));

vi.mock('@/hooks/useCommands', () => ({
  useCommands: () => ({
    commands: [],
    execute: vi.fn(),
    getSuggestions: vi.fn().mockReturnValue([]),
    isLoading: false,
    error: null,
    fetchCommands: vi.fn(),
  }),
}));

vi.mock('@/components/chat/ThinkingStream', () => ({
  useThinkingStream: () => ({
    agents: new Map(),
    processChunk: vi.fn(),
    reset: vi.fn(),
  }),
}));

vi.mock('@/components/auth/ShareDialog', () => ({
  default: ({ open }: { open: boolean }) =>
    open ? <div data-testid="share-dialog-mock">ShareDialog</div> : null,
}));

vi.mock('@/plugins/slots', () => ({
  PluginSlot: () => null,
}));

// MSW handlers for ChatPage API calls
const chatPageHandlers = [
  http.get('/api/chat/conversations', () => {
    return HttpResponse.json({ conversations: [], total: 0 });
  }),
  http.get('/api/projects', () => {
    return HttpResponse.json({ projects: [], total: 0 });
  }),
  http.get('/api/chat/:id/stream-status', () => {
    return HttpResponse.json({ active: false, accumulated_content: null, accumulated_thinking: null });
  }),
  http.get('/api/plans', () => {
    return HttpResponse.json({ items: [], total: 0 });
  }),
];

// Helper to render ChatPage with router context and providers
const renderChatPage = (conversationId?: string) => {
  const path = conversationId ? `/chat/${conversationId}` : '/chat';
  return render(
    <TooltipProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/chat/:id" element={<ChatPage />} />
        </Routes>
      </MemoryRouter>
    </TooltipProvider>
  );
};

describe('Chat Message Flow Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.setItem('auth_tokens', JSON.stringify({
      access_token: 'test-token',
      refresh_token: 'test-refresh',
    }));
    server.use(...chatPageHandlers);
  });

  afterEach(() => {
    cleanup();
    localStorage.clear();
  });

  describe('Message rendering', () => {
    it('renders messages from API in correct chronological order', async () => {
      // Mock conversation messages with specific order
      server.use(
        http.get('/api/chat/history/:id', () => {
          return HttpResponse.json({
            messages: [
              {
                id: 'msg-1',
                role: 'user',
                content: 'First message from user',
                created_at: '2026-01-01T10:00:00Z',
                tool_calls: [],
              },
              {
                id: 'msg-2',
                role: 'assistant',
                content: 'First response from assistant',
                created_at: '2026-01-01T10:00:01Z',
                tool_calls: [],
              },
              {
                id: 'msg-3',
                role: 'user',
                content: 'Second message from user',
                created_at: '2026-01-01T10:01:00Z',
                tool_calls: [],
              },
              {
                id: 'msg-4',
                role: 'assistant',
                content: 'Second response from assistant',
                created_at: '2026-01-01T10:01:01Z',
                tool_calls: [],
              },
            ],
            total: 4,
          });
        })
      );

      renderChatPage('conv-123');

      // Wait for messages to load and verify order
      await waitFor(() => {
        expect(screen.getByText('First message from user')).toBeInTheDocument();
      });

      // All messages should be present
      expect(screen.getByText('First response from assistant')).toBeInTheDocument();
      expect(screen.getByText('Second message from user')).toBeInTheDocument();
      expect(screen.getByText('Second response from assistant')).toBeInTheDocument();

      // Verify order: first user message appears before second user message in DOM
      const firstUser = screen.getByText('First message from user');
      const secondUser = screen.getByText('Second message from user');
      // compareDocumentPosition returns a bitmask, bit 4 means "follows"
      expect(firstUser.compareDocumentPosition(secondUser) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    });

    it('shows EmptyState component when conversation has no user messages', async () => {
      // New conversation (no ID) shows empty state
      renderChatPage();

      await waitFor(() => {
        expect(screen.getByText('How can I help?')).toBeInTheDocument();
      });

      // EmptyState shows description and suggestions
      expect(screen.getByText(/Build workflows, configure agents/i)).toBeInTheDocument();
      expect(screen.getByText('Create a workflow')).toBeInTheDocument();
      expect(screen.getByText('Configure agents')).toBeInTheDocument();
      expect(screen.getByText('Analyze data')).toBeInTheDocument();
      expect(screen.getByText('Ask a question')).toBeInTheDocument();
    });
  });

  describe('Message input', () => {
    it('accepts text input and reflects it in the input field', async () => {
      const user = userEvent.setup();
      renderChatPage();

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/Message Dryade/i)).toBeInTheDocument();
      });

      const input = screen.getByPlaceholderText(/Message Dryade/i);
      await user.type(input, 'Hello, this is a test message');
      expect(input).toHaveValue('Hello, this is a test message');
    });

    it('clears input after sending a message', async () => {
      const user = userEvent.setup();

      // Mock conversation creation endpoint
      server.use(
        http.post('/api/chat/conversations', () => {
          return HttpResponse.json({
            id: 'new-conv-id',
            title: 'New Conversation',
            mode: 'chat',
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          });
        }),
        http.patch('/api/chat/conversations/:id', () => {
          return HttpResponse.json({
            id: 'new-conv-id',
            title: 'Hello from test',
            mode: 'chat',
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          });
        })
      );

      renderChatPage();

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/Message Dryade/i)).toBeInTheDocument();
      });

      const input = screen.getByPlaceholderText(/Message Dryade/i);
      await user.type(input, 'Hello from test');
      await user.keyboard('{Enter}');

      // Input should be cleared after send
      await waitFor(() => {
        expect(input).toHaveValue('');
      });
    });
  });

  describe('EmptyState component', () => {
    it('renders with correct variant props', () => {
      const onSuggestionClick = vi.fn();

      render(
        <EmptyState
          variant="chat"
          title="Test Empty State"
          description="Test description"
          suggestions={chatSuggestions}
          onSuggestionClick={onSuggestionClick}
        />
      );

      expect(screen.getByText('Test Empty State')).toBeInTheDocument();
      expect(screen.getByText('Test description')).toBeInTheDocument();
    });

    it('calls onSuggestionClick with correct prompt when suggestion clicked', async () => {
      const user = userEvent.setup();
      const onSuggestionClick = vi.fn();

      render(
        <EmptyState
          variant="chat"
          title="How can I help?"
          suggestions={chatSuggestions}
          onSuggestionClick={onSuggestionClick}
        />
      );

      // Click the "Create a workflow" suggestion
      const createBtn = screen.getByText('Create a workflow');
      await user.click(createBtn);

      expect(onSuggestionClick).toHaveBeenCalledWith('Help me create a new workflow');
    });

    it('renders all 4 default chat suggestions', () => {
      render(
        <EmptyState
          variant="chat"
          title="Test"
          suggestions={chatSuggestions}
          onSuggestionClick={vi.fn()}
        />
      );

      expect(screen.getByText('Create a workflow')).toBeInTheDocument();
      expect(screen.getByText('Configure agents')).toBeInTheDocument();
      expect(screen.getByText('Analyze data')).toBeInTheDocument();
      expect(screen.getByText('Ask a question')).toBeInTheDocument();
    });
  });
});
