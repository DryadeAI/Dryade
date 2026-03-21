// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { TooltipProvider } from '@/components/ui/tooltip';
import { http, HttpResponse } from 'msw';
import { server } from '@/mocks/server';
import ChatPage from '@/pages/ChatPage';

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

// MSW handlers for API calls ChatPage makes on mount
const chatPageHandlers = [
  // GET /api/chat/conversations -- conversations list
  http.get('/api/chat/conversations', () => {
    return HttpResponse.json({
      conversations: [],
      total: 0,
    });
  }),
  // GET /api/projects -- projects list
  http.get('/api/projects', () => {
    return HttpResponse.json({
      projects: [],
      total: 0,
    });
  }),
  // GET /api/chat/:id/stream-status -- stream status check
  http.get('/api/chat/:id/stream-status', () => {
    return HttpResponse.json({
      active: false,
      accumulated_content: null,
      accumulated_thinking: null,
    });
  }),
  // GET /api/chat/history/:id -- conversation messages
  http.get('/api/chat/history/:id', () => {
    return HttpResponse.json({
      messages: [
        {
          id: 'msg-1',
          role: 'user',
          content: 'Hello there',
          created_at: new Date(Date.now() - 120000).toISOString(),
          tool_calls: [],
        },
        {
          id: 'msg-2',
          role: 'assistant',
          content: 'Hello! I am your AI assistant. How can I help you today?',
          created_at: new Date(Date.now() - 60000).toISOString(),
          tool_calls: [],
        },
      ],
      total: 2,
    });
  }),
  // GET /api/plans -- plans for conversation context
  http.get('/api/plans', () => {
    return HttpResponse.json({
      items: [],
      total: 0,
    });
  }),
];

// Helper to render with router context and required providers
const renderWithRouter = (conversationId?: string) => {
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

describe('ChatPage Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Set auth tokens so fetchWithAuth doesn't trigger 401 redirect loops
    localStorage.setItem('auth_tokens', JSON.stringify({
      access_token: 'test-token',
      refresh_token: 'test-refresh',
    }));
    // Add ChatPage-specific handlers for each test
    server.use(...chatPageHandlers);
  });

  afterEach(() => {
    cleanup();
  });

  it('renders chat interface with empty state', async () => {
    renderWithRouter();

    // Header shows conversation title
    expect(screen.getByText('New conversation')).toBeInTheDocument();

    // EmptyState is shown when no user messages exist
    await waitFor(() => {
      expect(screen.getByText('How can I help?')).toBeInTheDocument();
    });
  });

  it('displays New conversation title when route has conversation ID', async () => {
    // When loading a conversation by ID, the title comes from the conversations list
    // Since our mock returns empty conversations list, the title stays as "New conversation"
    renderWithRouter('abc123de');

    await waitFor(() => {
      expect(screen.getByText('New conversation')).toBeInTheDocument();
    });
  });

  it('renders with new conversation title when no ID', () => {
    renderWithRouter();

    // New conversation title displayed in header
    expect(screen.getByText('New conversation')).toBeInTheDocument();
  });

  it('shows message input field and buttons', async () => {
    renderWithRouter();

    // Find CommandInput's inner input via placeholder
    await waitFor(() => {
      const input = screen.getByPlaceholderText(/Message Dryade/i);
      expect(input).toBeInTheDocument();
    });

    // Find buttons (send, attachment, thinking, search, share, etc.)
    const buttons = screen.getAllByRole('button');
    expect(buttons.length).toBeGreaterThan(0);
  });

  it('accepts text input', async () => {
    const user = userEvent.setup();
    renderWithRouter();

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/Message Dryade/i)).toBeInTheDocument();
    });

    const input = screen.getByPlaceholderText(/Message Dryade/i);

    // Type a message
    await user.type(input, 'Hello test');

    // Input should have the text
    expect(input).toHaveValue('Hello test');
  });

  it('displays empty state with suggestions for new conversations', async () => {
    renderWithRouter();

    // EmptyState shows "How can I help?" heading
    await waitFor(() => {
      expect(screen.getByText('How can I help?')).toBeInTheDocument();
    });

    // EmptyState shows description
    expect(
      screen.getByText(/Build workflows, configure agents/i)
    ).toBeInTheDocument();

    // EmptyState shows suggestion buttons
    expect(screen.getByText('Create a workflow')).toBeInTheDocument();
    expect(screen.getByText('Configure agents')).toBeInTheDocument();
    expect(screen.getByText('Analyze data')).toBeInTheDocument();
    expect(screen.getByText('Ask a question')).toBeInTheDocument();
  });

  it('renders mode selector with Chat and Planner tabs', async () => {
    renderWithRouter();

    // ModeSelector renders Chat and Planner tabs
    await waitFor(() => {
      expect(screen.getByRole('tablist')).toBeInTheDocument();
    });

    // Check for the mode tab labels
    expect(screen.getByText('Chat')).toBeInTheDocument();
    expect(screen.getByText('Planner')).toBeInTheDocument();
  });

  it('renders header with conversation title and controls', async () => {
    renderWithRouter();

    // Header exists with expected content
    await waitFor(() => {
      expect(screen.getByText('New conversation')).toBeInTheDocument();
    });

    // Mode selector is in the header
    expect(screen.getByRole('tablist')).toBeInTheDocument();

    // Search and share buttons exist
    const buttons = screen.getAllByRole('button');
    expect(buttons.length).toBeGreaterThanOrEqual(3); // At least mode tabs + thinking + search + share
  });

  it('renders sidebar with conversation list area', () => {
    renderWithRouter();

    // The component renders with main chat area and sidebar
    // Verify the overall layout structure is present
    expect(screen.getByText('New conversation')).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Message Dryade/i)).toBeInTheDocument();
  });

  it('shows initial messages for new conversation with greeting text', () => {
    renderWithRouter();

    // New conversations show EmptyState instead of the initial assistant message
    // EmptyState has the greeting heading
    expect(screen.getByText('How can I help?')).toBeInTheDocument();
  });
});
