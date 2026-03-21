// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useRef, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useParams, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import CommandPalette from "@/components/chat/CommandPalette";
import ChatHeader from "@/components/chat/ChatHeader";
import MessageItem from "@/components/chat/MessageItem";
import ShareDialog from "@/components/auth/ShareDialog";
import UnifiedSidebar from "@/components/chat/UnifiedSidebar";
import ExecutionSidebar from "@/components/execution/ExecutionSidebar";
import CompletionModal from "@/components/execution/CompletionModal";
import { PlanResultModal, parsePlanExports } from "@/components/chat/PlanPanel";
import CommandInput from "@/components/chat/CommandInput";
import EmptyState, { chatSuggestions } from "@/components/shared/EmptyState";
import { useThinkingStream } from "@/components/chat/ThinkingStream";
import { type AgentStreamChunk } from "@/types/streaming";
import { useLocalStorage } from "@/hooks/useLocalStorage";
import { useCommands } from "@/hooks/useCommands";
import { useCommandExecution } from "@/hooks/useCommandExecution";
import { useExecutionStream } from "@/hooks/useExecutionStream";
import { useChatState } from "@/hooks/useChatState";
import { toast } from "sonner";
import { useChatWebSocket, type WSEvent } from "@/hooks/useChatWebSocket";
import { getTokens } from "@/services/apiClient";
import { chatApi } from "@/services/api";
import { showFailoverToast } from "@/components/chat/FailoverToast";
import { AllProvidersDown } from "@/components/chat/AllProvidersDown";
import type { Message } from "@/components/chat/MessageItem";
import PlanCard from "@/components/chat/PlanCard";
import type { ExecutionStatus } from "@/types/execution";
import { Paperclip, ArrowDown, Bot } from "lucide-react";
import { PluginSlot } from "@/plugins/slots";

/** Typing indicator component shown before first token — three-dot bounce animation */
const TypingIndicator = () => {
  return (
    <div className="flex gap-2 motion-safe:animate-fade-in" role="status" aria-label="Assistant is thinking">
      <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 mt-0.5 bg-primary/10">
        <Bot size={16} className="text-primary" />
      </div>
      <div className="mr-auto flex items-center gap-1 py-2.5">
        <span className="w-1.5 h-1.5 rounded-full bg-primary/70 motion-safe:animate-bounce [animation-delay:0ms]" />
        <span className="w-1.5 h-1.5 rounded-full bg-primary/70 motion-safe:animate-bounce [animation-delay:150ms]" />
        <span className="w-1.5 h-1.5 rounded-full bg-primary/70 motion-safe:animate-bounce [animation-delay:300ms]" />
      </div>
    </div>
  );
};

const ChatPage = () => {
  const { t } = useTranslation('chat');
  const { id: conversationId } = useParams<{ id: string }>();
  const navigate = useNavigate();

  // UI-only state (kept in ChatPage)
  const [panelCollapsed, setPanelCollapsed] = useLocalStorage("chat-panel-collapsed", false);
  const [input, setInput] = useState("");
  const [editingInput, setEditingInput] = useState("");
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [showScrollButton, setShowScrollButton] = useState(false);
  const [userScrolled, setUserScrolled] = useState(false);
  const [viewMode, setViewMode] = useState<"rendered" | "raw">("rendered");
  const [enableThinking, setEnableThinking] = useState(false);
  const [eventVisibility, setEventVisibility] = useState<string>("named-steps");
  const [shareDialogOpen, setShareDialogOpen] = useState(false);
  const [inputFocused, setInputFocused] = useState(false);
  const [sidebarMode, setSidebarMode] = useState<'catalog' | 'execution'>('catalog');
  const [showCompletionModal, setShowCompletionModal] = useState(false);
  const [allProvidersDown, setAllProvidersDown] = useState(false);

  // Command discovery and execution hook
  const { commands, execute: executeCommand, getSuggestions, isLoading: commandsLoading } = useCommands();

  // Execution stream hook for workflow visibility
  const execution = useExecutionStream();

  // Agent thinking stream hook for crew mode visibility
  const { agents, processChunk: processAgentChunk, reset: resetThinkingStream } = useThinkingStream();

  // Chat state management hook (conversations, messages, projects, handlers)
  const selectedProjectIdStorage = useLocalStorage<string | null>("selected-project", null);
  const chatState = useChatState({
    conversationId,
    searchQuery,
    editingInput,
    setEditingInput,
    copiedId,
    setCopiedId,
    resetThinkingStream,
    selectedProjectIdStorage,
  });

  const {
    conversations,
    setConversations,
    conversationsLoading,
    conversationTitle,
    setConversationTitle,
    projects,
    selectedProjectId,
    setSelectedProjectId,
    messages,
    setMessages,
    isLoading,
    setIsLoading,
    streamingAssistantId,
    setStreamingAssistantId,
    currentPlan,
    setCurrentPlan,
    planResultModalOpen,
    setPlanResultModalOpen,
    selectedPlanResult,
    selectedPlanName,
    chatMode,
    setChatMode,
    filteredMessages,
    groupedMessages,
    showEmptyState,
    isLoadingConversation,
    handleSelectConversation,
    handleNewChat,
    handleDeleteConversation,
    handleRenameConversation,
    handleBulkDeleteConversations,
    handleDeleteAllConversations,
    handleCreateProject,
    handleUpdateProject,
    handleDeleteProject,
    handleMoveConversation,
    handleDeleteProjectConversations,
    handleCopy,
    handleEdit,
    handleSaveEdit,
    handleCancelEdit,
    handleDelete,
    handleFeedback,
    handleViewPlanResults,
    justCreatedConvRef,
    generateTitle,
    initialMessages,
  } = chatState;

  // Command execution hook (palette state + execute/select handlers)
  const {
    isExecutingCommand,
    commandOpen,
    setCommandOpen,
    handleCommandExecute,
    handleCommandSelect,
  } = useCommandExecution({
    executeCommand,
    setMessages,
    setInput,
    setUserScrolled,
  });

  const toggleVisibility = useCallback(() => {
    setEventVisibility(prev => prev === "full-transparency" ? "named-steps" : "full-transparency");
  }, []);

  // Ref to track latest agents state for use in WS event handler (avoids closure staleness)
  const agentsRef = useRef(agents);
  agentsRef.current = agents;

  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  // AbortController for stopping generation (SSE fallback only)
  const abortControllerRef = useRef<AbortController | null>(null);

  // Refs for WS streaming accumulation (stable across renders)
  const wsStreamedContentRef = useRef("");
  const wsStreamedThinkingRef = useRef("");
  const wsAssistantIdRef = useRef<string | null>(null);
  const wsAssistantCreatedRef = useRef(false);
  // Ignore stale events arriving after user clicked stop
  const wsCancelledRef = useRef(false);
  // RAF-based throttling for streaming token updates (PERF-03)
  // Batches rapid token events to ~60fps instead of updating state per token
  const rafIdRef = useRef<number | null>(null);
  const rafDirtyRef = useRef(false);

  // WebSocket event handler - maps WS events to the same state updates as SSE
  const handleWSEvent = useCallback((event: WSEvent) => {
    const { type, data } = event;

    // Drop stale events after user cancelled (except cancel_ack itself)
    if (wsCancelledRef.current && type !== "cancel_ack" && type !== "complete") {
      return;
    }

    // Helper to create or update the assistant message
    const updateAssistantMessage = () => {
      const id = wsAssistantIdRef.current;
      if (!id) return;
      const content = wsStreamedContentRef.current;
      const thinking = wsStreamedThinkingRef.current || undefined;

      if (!wsAssistantCreatedRef.current) {
        const assistantMessage: Message = {
          id,
          role: "assistant",
          content,
          thinking,
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, assistantMessage]);
        setStreamingAssistantId(id);
        wsAssistantCreatedRef.current = true;
      } else {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === id ? { ...m, content, thinking } : m
          )
        );
      }
    };

    // Helper: schedule a batched state update via requestAnimationFrame (PERF-03)
    // Multiple token/thinking events within one frame are coalesced into a single setMessages call
    const scheduleUpdate = () => {
      rafDirtyRef.current = true;
      if (rafIdRef.current === null) {
        rafIdRef.current = requestAnimationFrame(() => {
          rafIdRef.current = null;
          if (rafDirtyRef.current) {
            rafDirtyRef.current = false;
            updateAssistantMessage();
          }
        });
      }
    };

    // Token / content events - accumulate text, throttled to ~60fps
    if (type === "token" || type === "content") {
      const tokenContent = (data.content as string) || "";
      if (tokenContent) {
        wsStreamedContentRef.current += tokenContent;
        scheduleUpdate();
      }
      return;
    }

    // Thinking events - accumulate, throttled to ~60fps
    if (type === "thinking") {
      const thinkingContent = (data.content as string) || "";
      if (thinkingContent) {
        wsStreamedThinkingRef.current += thinkingContent;
        scheduleUpdate();
      }
      processAgentChunk({ type: "thinking", agent: "assistant", content: thinkingContent } as AgentStreamChunk);
      return;
    }

    // Agent events - forward to ThinkingStream
    if (["agent_start", "agent_complete", "tool_start", "tool_result", "escalation", "reasoning", "progress"].includes(type)) {
      const chunk = { type, ...data, timestamp: new Date().toISOString() } as AgentStreamChunk;
      processAgentChunk(chunk);

      if (type === "escalation") {
        const question = (data.content as string) || t('escalation.howToProceed');
        const context = data.task_context ? `\n\n_Task: ${data.task_context}_` : "";
        const fixDesc = data.auto_fix_description as string | undefined;
        const autoFixHint = data.has_auto_fix
          ? `\n\n${fixDesc ? `${t('escalation.suggestedFix', { description: fixDesc })}\n\n` : ''}${t('escalation.autoFixHint')}`
          : "";
        wsStreamedContentRef.current += `\n\n${t('escalation.needHelp')}\n\n${question}${context}${autoFixHint}`;
        updateAssistantMessage();
      }
      if (type === "reasoning" && data.content) {
        wsStreamedThinkingRef.current += `\n${data.content}`;
        updateAssistantMessage();
      }
      return;
    }

    // Complete event - finalize (flush any pending RAF first)
    if (type === "complete") {
      // Cancel pending RAF and flush immediately - ensures final content is rendered
      if (rafIdRef.current !== null) {
        cancelAnimationFrame(rafIdRef.current);
        rafIdRef.current = null;
        rafDirtyRef.current = false;
      }
      if (data.content) {
        wsStreamedContentRef.current = data.content as string;
        updateAssistantMessage();
      }

      // Handle plan data from planner mode (emitted by PlannerHandler)
      const exports = data.exports as Record<string, unknown> | undefined;
      const planCardData = parsePlanExports(exports);
      if (planCardData) {
        setCurrentPlan(planCardData);

        // Attach plan data to the assistant message
        if (wsAssistantIdRef.current) {
          const msgId = wsAssistantIdRef.current;
          setMessages((prev) =>
            prev.map((m) =>
              m.id === msgId ? { ...m, planData: planCardData } : m
            )
          );
        }
      }

      // Persist planner mode to conversation for session restoration
      if (exports?.mode === "planner" && conversationId) {
        chatApi.updateConversation(conversationId, { mode: 'planner' }).catch(console.error);
      }

      // Persist agents into message using ref to avoid closure staleness
      const currentAgents = agentsRef.current;
      if (currentAgents.size > 0 && wsAssistantIdRef.current) {
        const msgId = wsAssistantIdRef.current;
        setMessages((prev) =>
          prev.map((m) =>
            m.id === msgId ? { ...m, agents: new Map(currentAgents) } : m
          )
        );
      }
      setIsLoading(false);
      setStreamingAssistantId(null);
      return;
    }

    // All providers exhausted — show inline degradation UI (must be before generic error handler)
    if (type === "error" && data.code === "all_providers_exhausted") {
      if (rafIdRef.current !== null) {
        cancelAnimationFrame(rafIdRef.current);
        rafIdRef.current = null;
        rafDirtyRef.current = false;
      }
      setAllProvidersDown(true);
      setIsLoading(false);
      setStreamingAssistantId(null);
      return;
    }

    // Error events - flush pending RAF before cleanup
    if (type === "error") {
      if (rafIdRef.current !== null) {
        cancelAnimationFrame(rafIdRef.current);
        rafIdRef.current = null;
        rafDirtyRef.current = false;
      }
      const errorMsg = (data.message as string) || "Unknown error";
      toast.error(t('page.streamError'), { description: errorMsg });
      setIsLoading(false);
      setStreamingAssistantId(null);
      return;
    }

    // Provider failover event — show toast with Stop button
    if (type === "failover") {
      const fromProvider = (data.from_provider as string) || "unknown";
      const toProvider = (data.to_provider as string) || "unknown";
      if (conversationId) {
        showFailoverToast(fromProvider, toProvider, conversationId);
      }
      return;
    }

    // Cancel acknowledgment - flush pending RAF then persist agents as safety net
    if (type === "cancel_ack") {
      if (rafIdRef.current !== null) {
        cancelAnimationFrame(rafIdRef.current);
        rafIdRef.current = null;
        rafDirtyRef.current = false;
      }
      const currentAgents = agentsRef.current;
      if (currentAgents.size > 0 && wsAssistantIdRef.current) {
        const msgId = wsAssistantIdRef.current;
        setMessages((prev) =>
          prev.map((m) =>
            m.id === msgId ? { ...m, agents: new Map(currentAgents) } : m
          )
        );
      }
      setIsLoading(false);
      setStreamingAssistantId(null);
      return;
    }
  }, [processAgentChunk, conversationId, setMessages, setIsLoading, setStreamingAssistantId, setCurrentPlan, setAllProvidersDown, t]);

  // WebSocket hook - connects when we have a conversationId
  const authToken = getTokens()?.access_token;
  const {
    status: wsStatus,
    latencyMs: wsLatency,
    reconnectAttempt: wsReconnectAttempt,
    maxReconnects: wsMaxReconnects,
    sendMessage: wsSendMessage,
    cancelStream: wsCancelStream,
    reconnect: wsReconnect,
  } = useChatWebSocket({
    conversationId: conversationId || "",
    token: authToken,
    onEvent: handleWSEvent,
    onError: (err) => {
      if (!err.startsWith("Rate limited")) {
        console.error("WS error:", err);
      }
    },
    enabled: !!conversationId,
  });

  // Map WS status to connection state for ConnectionStatus component
  const connectionState = wsStatus === "connected" ? "connected"
    : wsStatus === "reconnecting" ? "reconnecting"
    : "disconnected";

  // Check for active stream on mount/navigation (reconnect recovery)
  useEffect(() => {
    if (!conversationId) return;
    chatApi.getStreamStatus(conversationId).then((status) => {
      if (status.active) {
        setIsLoading(true);
        if (status.accumulated_content || status.accumulated_thinking) {
          const id = `msg-resumed-${Date.now()}`;
          wsAssistantIdRef.current = id;
          wsAssistantCreatedRef.current = true;
          wsStreamedContentRef.current = status.accumulated_content || "";
          wsStreamedThinkingRef.current = status.accumulated_thinking || "";
          setStreamingAssistantId(id);
          setMessages((prev) => [...prev, {
            id,
            role: "assistant" as const,
            content: status.accumulated_content || "",
            thinking: status.accumulated_thinking || undefined,
            timestamp: new Date(),
          }]);
        }
      }
    }).catch(() => {});
  }, [conversationId, setIsLoading, setStreamingAssistantId, setMessages]);

  // Cleanup abort controller and RAF on unmount
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
      if (rafIdRef.current !== null) {
        cancelAnimationFrame(rafIdRef.current);
        rafIdRef.current = null;
      }
    };
  }, []);

  // Auto-scroll only if user hasn't scrolled up
  const scrollToBottom = useCallback(() => {
    if (!userScrolled) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [userScrolled]);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  // Track scroll position
  const handleScroll = useCallback(() => {
    const container = messagesContainerRef.current;
    if (!container) return;

    const { scrollTop, scrollHeight, clientHeight } = container;
    const isNearBottom = scrollHeight - scrollTop - clientHeight < 100;

    setShowScrollButton(!isNearBottom);
    setUserScrolled(!isNearBottom);
  }, []);

  // Keyboard shortcut: Ctrl+F for search (Ctrl+K handled by useCommandExecution)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "f") {
        e.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  /**
   * Handle sending a regular chat message.
   */
  const handleSend = useCallback(async (messageContent?: string, imageAttachments?: Array<{ base64: string; mime_type: string }>) => {
    const content = (messageContent || input).trim();
    if (!content || isLoading) return;

    const userMessage: Message = {
      id: `msg-${Date.now()}`,
      role: "user",
      content,
      timestamp: new Date(),
    };

    const isFirstUserMessage = messages.filter((m) => m.role === "user").length === 0;

    if (isFirstUserMessage) {
      setMessages([userMessage]);
    } else {
      setMessages((prev) => [...prev, userMessage]);
    }
    setInput("");
    setIsLoading(true);
    setUserScrolled(false);

    try {
      let activeConversationId = conversationId;

      if (!activeConversationId) {
        const newConv = await chatApi.createConversation(chatMode);
        setConversations((prev) => [newConv, ...prev]);
        activeConversationId = newConv.id;
        justCreatedConvRef.current = newConv.id;
        navigate(`/workspace/chat/${newConv.id}`, { replace: true });
      }

      if (isFirstUserMessage && activeConversationId) {
        const title = generateTitle(content);
        chatApi.updateConversation(activeConversationId, { title })
          .then(() => {
            setConversationTitle(title);
            setConversations((prev) =>
              prev.map((c) => (c.id === activeConversationId ? { ...c, title } : c))
            );
          })
          .catch(console.error);
      }

      wsCancelledRef.current = false;
      const assistantMessageId = `msg-${Date.now()}-assistant`;
      wsAssistantIdRef.current = assistantMessageId;
      wsAssistantCreatedRef.current = false;
      wsStreamedContentRef.current = "";
      wsStreamedThinkingRef.current = "";

      wsSendMessage(content, {
        mode: chatMode,
        enable_thinking: enableThinking,
        event_visibility: eventVisibility,
        image_attachments: imageAttachments,
      });
    } catch (error) {
      console.error("Failed to send message:", error);
      const errorMsg = error instanceof Error ? error.message : t('page.connectionError');
      const errorAssistantId = `${Date.now()}-error`;
      setMessages((prev) => {
        const cleaned = prev.filter((m) => !m.id?.endsWith("-assistant"));
        return [
          ...cleaned,
          {
            id: errorAssistantId,
            role: "assistant" as const,
            content: `**Error:** ${errorMsg}`,
            timestamp: new Date(),
            error: errorMsg,
            failedContent: content,
          },
        ];
      });
      toast.error(t('page.failedToSend'), { description: errorMsg });
      setIsLoading(false);
      setStreamingAssistantId(null);
    }
  }, [input, isLoading, conversationId, chatMode, enableThinking, eventVisibility, navigate, messages, wsSendMessage, setMessages, setIsLoading, setStreamingAssistantId, setConversations, setConversationTitle, justCreatedConvRef, generateTitle, t]);

  /**
   * Stop generation by cancelling via WebSocket.
   */
  const handleStopGeneration = useCallback(() => {
    const currentAgents = agentsRef.current;
    if (currentAgents.size > 0 && wsAssistantIdRef.current) {
      const msgId = wsAssistantIdRef.current;
      setMessages((prev) =>
        prev.map((m) =>
          m.id === msgId ? { ...m, agents: new Map(currentAgents) } : m
        )
      );
    }
    wsCancelledRef.current = true;
    wsCancelStream();
    if (chatMode !== "planner" && conversationId) {
      chatApi.cancelOrchestration(conversationId).catch(() => {});
    }
    setIsLoading(false);
    setStreamingAssistantId(null);
  }, [wsCancelStream, chatMode, conversationId, setMessages, setIsLoading, setStreamingAssistantId]);

  const handleRegenerate = async (id: string) => {
    const idx = messages.findIndex((m) => m.id === id);
    if (idx === -1 || !conversationId) return;

    let userMessageIdx = -1;
    for (let i = idx - 1; i >= 0; i--) {
      if (messages[i].role === "user") {
        userMessageIdx = i;
        break;
      }
    }
    if (userMessageIdx === -1) return;

    const userMessage = messages[userMessageIdx];

    setMessages((prev) => prev.slice(0, userMessageIdx));
    setIsLoading(true);

    setMessages((prev) => [...prev, userMessage]);

    const assistantMessageId = `msg-${Date.now()}-assistant`;
    wsAssistantIdRef.current = assistantMessageId;
    wsAssistantCreatedRef.current = false;
    wsStreamedContentRef.current = "";
    wsStreamedThinkingRef.current = "";

    wsSendMessage(userMessage.content, {
      mode: chatMode,
      enable_thinking: enableThinking,
      event_visibility: eventVisibility,
    });
  };

  const handleRetry = useCallback((failedContent: string, errorMsgId: string) => {
    // Remove the error message and resend
    setMessages((prev) => prev.filter((m) => m.id !== errorMsgId));
    handleSend(failedContent);
  }, [handleSend, setMessages]);

  const forceScrollToBottom = () => {
    setUserScrolled(false);
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  /**
   * Export conversation as Markdown file
   */
  const handleExportConversation = useCallback(() => {
    if (messages.length === 0) return;
    const md = messages
      .map((m) => `## ${m.role === "user" ? t('page.userRole') : t('page.agentRole')}\n\n${m.content}`)
      .join("\n\n---\n\n");
    const blob = new Blob([md], { type: "text/markdown;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${conversationTitle || "conversation"}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }, [messages, conversationTitle, t]);

  /**
   * Trigger a workflow scenario execution and switch sidebar to execution mode
   */
  const handleTriggerScenario = useCallback(async (scenarioName: string, inputs: Record<string, unknown>) => {
    setSidebarMode('execution');
    await execution.startExecution(scenarioName, inputs);
  }, [execution]);

  /**
   * Close execution sidebar and return to catalog
   */
  const handleCloseExecution = useCallback(() => {
    setSidebarMode('catalog');
    execution.reset();
  }, [execution]);

  // Show completion modal when execution finishes
  useEffect(() => {
    if (execution.isComplete && sidebarMode === 'execution') {
      setShowCompletionModal(true);
    }
  }, [execution.isComplete, sidebarMode]);

  /**
   * Handle running the same scenario again
   */
  const handleRunAgain = useCallback(() => {
    if (execution.scenarioName) {
      const scenarioName = execution.scenarioName;
      execution.reset();
      execution.startExecution(scenarioName, {});
    }
  }, [execution]);

  /**
   * Close completion modal and return sidebar to catalog
   */
  const handleCompletionModalClose = useCallback(() => {
    setShowCompletionModal(false);
    setSidebarMode('catalog');
    execution.reset();
  }, [execution]);

  // Expose trigger function for external components (workflow triggers, etc.)
  useEffect(() => {
    if (import.meta.env.DEV) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (window as any).__triggerScenario = handleTriggerScenario;
      return () => {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        delete (window as any).__triggerScenario;
      };
    }
  }, [handleTriggerScenario]);

  return (
    <div className="h-full flex">
      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header + Search Bar */}
        <ChatHeader
          conversationTitle={conversationTitle}
          connectionState={connectionState}
          wsLatency={wsLatency ?? undefined}
          wsReconnectAttempt={wsReconnectAttempt}
          wsMaxReconnects={wsMaxReconnects}
          onReconnect={wsReconnect}
          chatMode={chatMode}
          onChatModeChange={(mode) => setChatMode(mode)}
          enableThinking={enableThinking}
          onToggleThinking={() => setEnableThinking(!enableThinking)}
          eventVisibility={eventVisibility}
          onToggleVisibility={toggleVisibility}
          searchOpen={searchOpen}
          onToggleSearch={() => setSearchOpen(!searchOpen)}
          onOpenShare={() => setShareDialogOpen(true)}
          searchQuery={searchQuery}
          onSearchQueryChange={setSearchQuery}
          onCloseSearch={() => {
            setSearchOpen(false);
            setSearchQuery("");
          }}
          filteredCount={filteredMessages?.length}
          onExport={messages.length > 0 ? handleExportConversation : undefined}
        />

      {/* Chat Container */}
      <div className="flex-1 flex flex-col min-h-0 relative">
        {/* Empty State, Loading, or Messages */}
        {isLoadingConversation ? (
          <div className="flex-1 flex items-center justify-center motion-safe:animate-fade-in">
            <div className="flex flex-col items-center gap-3">
              <div className="flex gap-1.5">
                <span className="w-2 h-2 rounded-full bg-primary/50 motion-safe:animate-bounce [animation-delay:0ms]" />
                <span className="w-2 h-2 rounded-full bg-primary/50 motion-safe:animate-bounce [animation-delay:150ms]" />
                <span className="w-2 h-2 rounded-full bg-primary/50 motion-safe:animate-bounce [animation-delay:300ms]" />
              </div>
            </div>
          </div>
        ) : showEmptyState ? (
          <EmptyState
            variant="chat"
            title={t('page.howCanIHelp')}
            description={t('page.emptyStateDescription')}
            suggestions={chatSuggestions}
            onSuggestionClick={(prompt) => {
              handleSend(prompt);
            }}
            className="flex-1 motion-safe:animate-fade-in"
          />
        ) : (
          <div
            ref={messagesContainerRef}
            onScroll={handleScroll}
            className="flex-1 overflow-y-auto motion-safe:animate-fade-in"
            role="log"
            aria-live="polite"
            aria-label="Conversation messages"
            data-testid="chat-message-list"
          >
            {/* Constrained message container for readable line lengths */}
            <div className="max-w-4xl mx-auto px-4 py-3 space-y-1.5">
            {groupedMessages.map(({ message, isGrouped, showAvatar }, idx) => {
              // Pass agents to the latest assistant message during streaming
              const isLatestAssistant = message.role === "assistant" && idx === groupedMessages.length - 1;
              const messageAgents = isLatestAssistant && isLoading && agents.size > 0 ? agents : undefined;
              const isMessageStreaming = isLatestAssistant && isLoading;

              return (
                <div key={message.id || `msg-fallback-${idx}`}>
                  <MessageItem
                    message={message}
                    isGrouped={isGrouped}
                    showAvatar={showAvatar}
                    copiedId={copiedId}
                    editingInput={editingInput}
                    viewMode={viewMode}
                    onCopy={handleCopy}
                    onEdit={handleEdit}
                    onSaveEdit={handleSaveEdit}
                    onCancelEdit={handleCancelEdit}
                    onEditingInputChange={setEditingInput}
                    onRegenerate={handleRegenerate}
                    onDelete={handleDelete}
                    onFeedback={handleFeedback}
                    onViewModeChange={setViewMode}
                    searchQuery={searchQuery}
                    agents={messageAgents}
                    isStreaming={isMessageStreaming}
                    onRetry={message.failedContent ? () => handleRetry(message.failedContent!, message.id) : undefined}
                  />
                  {/* Phase 70-04: Render PlanCard for planner mode messages */}
                  {message.planData && (
                    <div className="mt-3 ml-11">
                      <PlanCard
                        plan={message.planData}
                        conversationId={conversationId}
                        onPlanSaved={(savedId) => {
                          setCurrentPlan(prev => prev ? { ...prev, id: savedId } : null);
                        }}
                        onViewResults={handleViewPlanResults}
                      />
                    </div>
                  )}
                </div>
              );
            })}

            {/* Typing indicator during loading/streaming - hide once assistant message exists */}
            {(isLoading || isExecutingCommand) && !streamingAssistantId && <TypingIndicator />}

            {/* All providers unavailable — shown when every LLM provider in the fallback chain has failed */}
            {allProvidersDown && (
              <AllProvidersDown
                onRetry={() => {
                  setAllProvidersDown(false);
                  // Re-send the last user message to retry
                  const lastUserMsg = messages.filter((m) => m.role === "user").at(-1);
                  if (lastUserMsg) {
                    wsSendMessage(lastUserMsg.content);
                    setIsLoading(true);
                  }
                }}
                onCancel={() => setAllProvidersDown(false)}
              />
            )}

            <div ref={messagesEndRef} />
            </div>
          </div>
        )}

        {/* Scroll to Latest Button */}
        {showScrollButton && (
          <Button
            variant="secondary"
            size="sm"
            className="absolute bottom-20 left-1/2 -translate-x-1/2 shadow-lg gap-1 motion-safe:animate-fade-in"
            onClick={forceScrollToBottom}
          >
            <ArrowDown size={14} />
            {t('page.scrollToLatest')}
          </Button>
        )}

        {/* Input Area - Compact */}
        <div className="px-4 py-3 border-t border-border bg-card/30">
          <div className="flex gap-2 items-center max-w-3xl mx-auto">
            {/* Attachment button - shown on focus */}
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  type="button"
                  disabled
                  title={t('input.fileAttachmentComingSoon')}
                  className={cn(
                    "h-8 w-8 shrink-0 transition-opacity duration-150",
                    inputFocused ? "opacity-100" : "opacity-40"
                  )}
                >
                  <Paperclip size={14} />
                </Button>
              </TooltipTrigger>
              <TooltipContent>{t('input.attachFile')}</TooltipContent>
            </Tooltip>

            {/* CommandInput with "/" autocomplete integrated */}
            <div className="flex-1">
              <CommandInput
                commands={commands}
                onCommandExecute={handleCommandExecute}
                onMessageSend={handleSend}
                isExecuting={isExecutingCommand}
                isLoading={isLoading}
                onStop={handleStopGeneration}
                disabled={false}
                placeholder={t('input.placeholder')}
                getSuggestions={getSuggestions}
                onFocus={() => setInputFocused(true)}
                onBlur={() => setInputFocused(false)}
              />
            </div>
          </div>
        </div>
      </div>
      </div>

      {/* Plugin slots for chat panel */}
      <PluginSlot
        name="chat-panel"
        hostData={{ conversationId }}
        className="border-l border-border"
      />

      {/* Right Panel - Unified Sidebar or Execution Sidebar */}
      {sidebarMode === 'execution' ? (
        <ExecutionSidebar
          scenarioName={execution.scenarioName}
          status={execution.status}
          nodes={execution.nodes}
          currentNodeId={execution.currentNodeId}
          startedAt={execution.startedAt}
          error={execution.error}
          onCancel={execution.cancelExecution}
          onClose={handleCloseExecution}
        />
      ) : (
        <UnifiedSidebar
          projects={projects}
          conversations={conversations}
          selectedProjectId={selectedProjectId}
          selectedConversationId={conversationId || null}
          onSelectProject={setSelectedProjectId}
          onSelectConversation={handleSelectConversation}
          onCreateProject={handleCreateProject}
          onUpdateProject={handleUpdateProject}
          onDeleteProject={handleDeleteProject}
          onDeleteConversation={handleDeleteConversation}
          onNewChat={handleNewChat}
          onMoveConversation={handleMoveConversation}
          onRenameConversation={handleRenameConversation}
          onBulkDeleteConversations={handleBulkDeleteConversations}
          onDeleteAllConversations={handleDeleteAllConversations}
          onDeleteProjectConversations={handleDeleteProjectConversations}
          isLoading={conversationsLoading}
          collapsed={panelCollapsed}
          onToggleCollapse={() => setPanelCollapsed(!panelCollapsed)}
        />
      )}

      {/* Command Palette - Uses backend commands from useCommands hook */}
      <CommandPalette
        open={commandOpen}
        onOpenChange={setCommandOpen}
        commands={commands}
        isLoading={commandsLoading}
        onSelectCommand={handleCommandSelect}
      />

      {/* Share Dialog */}
      <ShareDialog
        open={shareDialogOpen}
        onOpenChange={setShareDialogOpen}
        resourceType="conversation"
        resourceId={conversationId || ""}
        resourceName={conversationTitle}
      />

      {/* Completion Modal */}
      <CompletionModal
        isOpen={showCompletionModal}
        onClose={handleCompletionModalClose}
        executionId={execution.executionId}
        scenarioName={execution.scenarioName}
        status={execution.status as ExecutionStatus}
        startedAt={execution.startedAt}
        completedAt={execution.completedAt}
        result={execution.finalResult}
        error={execution.error}
        onRunAgain={handleRunAgain}
      />

      {/* Plan Execution Result Modal */}
      <PlanResultModal
        open={planResultModalOpen}
        onOpenChange={setPlanResultModalOpen}
        selectedPlanResult={selectedPlanResult}
        selectedPlanName={selectedPlanName}
      />
    </div>
  );
};

export default ChatPage;
