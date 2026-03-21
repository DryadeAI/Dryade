// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { chatApi, projectsApi, plansApi } from "@/services/api";
import type { ChatMode, Conversation, Project } from "@/types/api";
import type { PlanCardData, PlanExecution } from "@/types/extended-api";
import type { Message } from "@/components/chat/MessageItem";

const LAST_CONVERSATION_KEY = "last-active-conversation";

const initialMessages: Message[] = [
  {
    id: "1",
    role: "assistant",
    content:
      "Hello! I'm your AI assistant. I can help you with workflow design, data analysis, and answering questions about your agents. How can I help you today?",
    timestamp: new Date(Date.now() - 60000),
    thinking: "Initializing conversation context and preparing to assist with workflow-related queries.",
    model: "gpt-4o",
  },
];

/** Map legacy modes to current 2-mode system */
const normalizeMode = (mode: string): ChatMode => {
  if (mode === "planner" || mode === "flow") return "planner";
  return "chat"; // chat, orchestrate, crew, autonomous -> chat
};

/** Generate a title from the first few words of a message */
const generateTitle = (content: string, maxWords = 6): string => {
  const words = content.trim().split(/\s+/).slice(0, maxWords);
  let title = words.join(" ");
  if (title.length > 50) {
    title = title.slice(0, 47) + "...";
  } else if (content.trim().split(/\s+/).length > maxWords) {
    title += "...";
  }
  return title || "New conversation";
};

/** Return type for useChatState hook */
export interface ChatState {
  // Conversation state
  conversations: Conversation[];
  setConversations: React.Dispatch<React.SetStateAction<Conversation[]>>;
  conversationsLoading: boolean;
  conversationTitle: string;
  setConversationTitle: React.Dispatch<React.SetStateAction<string>>;

  // Project state
  projects: Project[];
  selectedProjectId: string | null;
  setSelectedProjectId: (id: string | null) => void;

  // Message state
  messages: Message[];
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
  isLoading: boolean;
  setIsLoading: React.Dispatch<React.SetStateAction<boolean>>;
  streamingAssistantId: string | null;
  setStreamingAssistantId: React.Dispatch<React.SetStateAction<string | null>>;

  // Plan state
  currentPlan: PlanCardData | null;
  setCurrentPlan: React.Dispatch<React.SetStateAction<PlanCardData | null>>;
  planResultModalOpen: boolean;
  setPlanResultModalOpen: React.Dispatch<React.SetStateAction<boolean>>;
  selectedPlanResult: PlanExecution | null;
  setSelectedPlanResult: React.Dispatch<React.SetStateAction<PlanExecution | null>>;
  selectedPlanName: string;
  setSelectedPlanName: React.Dispatch<React.SetStateAction<string>>;

  // Chat mode
  chatMode: ChatMode;
  setChatMode: React.Dispatch<React.SetStateAction<ChatMode>>;

  // Loading state
  isLoadingConversation: boolean;

  // Computed values
  filteredMessages: Message[] | null;
  groupedMessages: Array<{ message: Message; isGrouped: boolean; showAvatar: boolean }>;
  showEmptyState: boolean;

  // Handlers - Conversation CRUD
  handleSelectConversation: (id: string) => void;
  handleNewChat: () => Promise<void>;
  handleDeleteConversation: (id: string) => Promise<void>;
  handleRenameConversation: (id: string, newTitle: string) => Promise<void>;
  handleBulkDeleteConversations: (ids: string[]) => Promise<void>;
  handleDeleteAllConversations: () => Promise<void>;

  // Handlers - Project CRUD
  handleCreateProject: (name: string) => Promise<void>;
  handleUpdateProject: (id: string, data: { name?: string }) => Promise<void>;
  handleDeleteProject: (id: string) => Promise<void>;
  handleMoveConversation: (conversationId: string, projectId: string | null) => Promise<void>;
  handleDeleteProjectConversations: (projectId: string) => Promise<void>;

  // Handlers - Message operations
  handleCopy: (content: string, id: string) => Promise<void>;
  handleEdit: (id: string) => void;
  handleSaveEdit: (id: string) => void;
  handleCancelEdit: (id: string) => void;
  handleDelete: (id: string) => void;
  handleFeedback: (id: string, type: "up" | "down") => void;
  handleViewPlanResults: (planId: number) => Promise<void>;

  // Refs needed by ChatPage for WS integration
  justCreatedConvRef: React.MutableRefObject<string | null>;

  // Utilities
  generateTitle: (content: string, maxWords?: number) => string;
  initialMessages: Message[];
}

export interface UseChatStateParams {
  conversationId: string | undefined;
  searchQuery: string;
  editingInput: string;
  setEditingInput: React.Dispatch<React.SetStateAction<string>>;
  copiedId: string | null;
  setCopiedId: React.Dispatch<React.SetStateAction<string | null>>;
  resetThinkingStream: () => void;
  selectedProjectIdStorage: [string | null, (value: string | null) => void];
}

export function useChatState({
  conversationId,
  searchQuery,
  editingInput,
  setEditingInput,
  copiedId,
  setCopiedId,
  resetThinkingStream,
  selectedProjectIdStorage,
}: UseChatStateParams): ChatState {
  const navigate = useNavigate();

  // Conversations state
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationsLoading, setConversationsLoading] = useState(true);
  const [conversationTitle, setConversationTitle] = useState<string>("New conversation");

  // Projects state
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = selectedProjectIdStorage;

  // Message state
  const [messages, setMessages] = useState<Message[]>(initialMessages);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingConversation, setIsLoadingConversation] = useState(false);
  const [streamingAssistantId, setStreamingAssistantId] = useState<string | null>(null);

  // Chat mode
  const [chatMode, setChatMode] = useState<ChatMode>("chat");

  // Plan state
  const [currentPlan, setCurrentPlan] = useState<PlanCardData | null>(null);
  const [planResultModalOpen, setPlanResultModalOpen] = useState(false);
  const [selectedPlanResult, setSelectedPlanResult] = useState<PlanExecution | null>(null);
  const [selectedPlanName, setSelectedPlanName] = useState<string>("");

  // Refs
  const lastModeSetForConvRef = useRef<string | null>(null);
  const justCreatedConvRef = useRef<string | null>(null);

  // ---------- Data loading effects ----------

  // Restore last active conversation when navigating to /workspace/chat (no :id)
  useEffect(() => {
    if (!conversationId) {
      try {
        const stored = localStorage.getItem(LAST_CONVERSATION_KEY);
        if (stored) {
          const lastId = JSON.parse(stored);
          if (lastId && typeof lastId === "string") {
            // Validate conversation still exists before navigating
            chatApi.getConversation(lastId)
              .then(() => {
                navigate(`/workspace/chat/${lastId}`, { replace: true });
              })
              .catch(() => {
                // Conversation no longer exists — clear stale reference
                localStorage.removeItem(LAST_CONVERSATION_KEY);
              });
          }
        }
      } catch {
        // Ignore parse errors
      }
    }
  }, [conversationId, navigate]);

  // Persist active conversation ID for cross-navigation recovery
  useEffect(() => {
    if (conversationId) {
      try {
        localStorage.setItem(LAST_CONVERSATION_KEY, JSON.stringify(conversationId));
      } catch {
        // Ignore storage errors
      }
    }
  }, [conversationId]);

  // Load conversations on mount
  useEffect(() => {
    setConversationsLoading(true);
    chatApi
      .getConversations({ limit: 50 })
      .then(({ conversations: data }) => setConversations(Array.isArray(data) ? data : []))
      .catch(() => setConversations([]))
      .finally(() => setConversationsLoading(false));
  }, []);

  // Load projects on mount
  useEffect(() => {
    projectsApi
      .getProjects()
      .then(({ projects: data }) => setProjects(Array.isArray(data) ? data : []))
      .catch(() => setProjects([]));
  }, []);

  // Update title and mode when conversations list loads/changes
  useEffect(() => {
    if (conversationId) {
      const conv = conversations.find((c) => c.id === conversationId);
      if (conv) {
        setConversationTitle(conv.title || "New conversation");
        if (lastModeSetForConvRef.current !== conversationId) {
          setChatMode(normalizeMode(conv.mode));
          lastModeSetForConvRef.current = conversationId;
        }
      }
    } else {
      lastModeSetForConvRef.current = null;
    }
  }, [conversationId, conversations]);

  // Load conversation messages when ID changes
  useEffect(() => {
    resetThinkingStream();
    setCurrentPlan(null);

    if (conversationId) {
      if (justCreatedConvRef.current === conversationId) {
        justCreatedConvRef.current = null;
        // Messages already set optimistically by handleSend — just mark loading done
        setIsLoadingConversation(false);
        return;
      }

      setIsLoadingConversation(true);
      setMessages([]);  // Clear stale messages immediately to prevent old conversation flash
      Promise.all([
        chatApi.getMessages(conversationId),
        plansApi.getPlans({ conversation_id: conversationId, limit: 10 }),
      ])
        .then(([{ messages: msgs }, plansResult]) => {
          const plans = Array.isArray(plansResult?.plans) ? plansResult.plans : [];
          const msgs2 = Array.isArray(msgs) ? msgs : [];
          const sortedPlans = plans.sort(
            (a, b) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime()
          );

          // Restore currentPlan from the latest plan
          if (sortedPlans.length > 0) {
            const latestPlan = sortedPlans[0];
            const planData: PlanCardData = {
              id: latestPlan.id,
              name: latestPlan.name,
              description: latestPlan.description || null,
              confidence: latestPlan.confidence || 0.8,
              nodes: (latestPlan.nodes ?? []).map((n) => ({
                id: n.id,
                agent: n.agent || n.label || n.id || "Task",
                task: n.description || n.label || "",
                position: undefined,
              })),
              edges: (latestPlan.edges ?? []).map((e) => ({
                from: e.source,
                to: e.target,
              })),
              status: latestPlan.status as PlanCardData["status"],
              ai_generated: latestPlan.ai_generated,
              created_at: latestPlan.created_at || new Date().toISOString(),
            };
            setCurrentPlan(planData);
          }

          // Convert messages and attach planData to assistant messages
          const converted: Message[] = msgs2.map((m) => {
            let agents:
              | Map<
                  string,
                  {
                    status: "complete" | "error";
                    capabilityStatus: "full";
                    content: string;
                    toolCalls: {
                      tool: string;
                      args?: Record<string, unknown>;
                      result?: string;
                      status: "complete" | "error";
                    }[];
                  }
                >
              | undefined;
            if (m.role === "assistant" && m.tool_calls && m.tool_calls.length > 0) {
              agents = new Map();
              const toolCalls = m.tool_calls.map((tc) => ({
                tool: tc.tool,
                args: tc.args,
                result: tc.result || undefined,
                status: (tc.status === "error" ? "error" : "complete") as "complete" | "error",
              }));
              agents.set("Orchestrator", {
                status: "complete",
                capabilityStatus: "full",
                content: "",
                toolCalls,
              });
            }

            const baseMessage: Message = {
              id: m.id,
              role: m.role as "user" | "assistant",
              content: m.content,
              timestamp: m.created_at ? new Date(m.created_at) : new Date(),
              thinking: m.thinking || undefined,
              agents,
            };

            if (
              m.role === "assistant" &&
              (m.content.includes("I've generated a workflow plan:") ||
                m.content.includes("I've updated the workflow plan"))
            ) {
              const planNameMatch = m.content.match(/\*\*([^*]+)\*\*/);
              const planName = planNameMatch?.[1];
              const matchingPlan = sortedPlans.find((p) => p.name === planName) || sortedPlans[0];

              if (matchingPlan) {
                baseMessage.planData = {
                  id: matchingPlan.id,
                  name: matchingPlan.name,
                  description: matchingPlan.description || null,
                  confidence: matchingPlan.confidence || 0.8,
                  nodes: matchingPlan.nodes.map((n) => ({
                    id: n.id,
                    agent: n.agent || n.label || n.id || "Task",
                    task: n.description || n.label || "",
                    position: undefined,
                  })),
                  edges: matchingPlan.edges.map((e) => ({
                    from: e.source,
                    to: e.target,
                  })),
                  status: matchingPlan.status as PlanCardData["status"],
                  ai_generated: matchingPlan.ai_generated,
                  created_at: matchingPlan.created_at || new Date().toISOString(),
                };
              }
            }

            return baseMessage;
          });

          setMessages(converted.length > 0 ? converted : initialMessages);
          setIsLoadingConversation(false);
        })
        .catch((error) => {
          console.error("Failed to load conversation data:", error);
          setMessages(initialMessages);
          setIsLoadingConversation(false);
          // Clear stale reference and navigate back on any fetch error
          // (404 not found, 401 auth expired, network error, etc.)
          localStorage.removeItem(LAST_CONVERSATION_KEY);
          navigate("/workspace/chat", { replace: true });
        });
    } else {
      // Don't reset messages if a send is in progress (handleSend sets messages
      // optimistically before the conversation is created and conversationId is set)
      setConversationTitle("New conversation");
      setMessages((prev) => {
        const hasUserMessages = prev.some((m) => m.role === "user");
        return hasUserMessages ? prev : initialMessages;
      });
    }
  }, [conversationId, resetThinkingStream, navigate]);

  // ---------- Computed values ----------

  const filteredMessages = useMemo(() => {
    if (!searchQuery.trim()) return null;
    const query = searchQuery.toLowerCase();
    return messages.filter((m) => m.content.toLowerCase().includes(query));
  }, [messages, searchQuery]);

  const groupedMessages = useMemo(() => {
    const displayMessages = filteredMessages || messages;
    return displayMessages.map((msg, idx) => {
      const prevMsg = idx > 0 ? displayMessages[idx - 1] : null;
      const isGrouped = prevMsg?.role === msg.role;
      const showAvatar = !isGrouped;
      return { message: msg, isGrouped, showAvatar };
    });
  }, [messages, filteredMessages]);

  const showEmptyState = useMemo(() => {
    if (isLoadingConversation) return false;
    const userMessages = messages.filter((m) => m.role === "user");
    return userMessages.length === 0;
  }, [messages, isLoadingConversation]);

  // ---------- Conversation handlers ----------

  const handleSelectConversation = useCallback(
    (id: string) => {
      navigate(`/workspace/chat/${id}`);
    },
    [navigate]
  );

  const handleNewChat = useCallback(async () => {
    try {
      const newConv = await chatApi.createConversation("chat");
      setConversations((prev) => [newConv, ...prev]);
      navigate(`/workspace/chat/${newConv.id}`);
    } catch (error) {
      console.error("Failed to create conversation:", error);
    }
  }, [navigate]);

  const handleDeleteConversation = useCallback(
    async (id: string) => {
      try {
        await chatApi.deleteConversation(id);
        setConversations((prev) => prev.filter((c) => c.id !== id));
        if (conversationId === id) {
          localStorage.removeItem(LAST_CONVERSATION_KEY);
          navigate("/workspace/chat");
        }
      } catch (error) {
        console.error("Failed to delete conversation:", error);
      }
    },
    [conversationId, navigate]
  );

  const handleRenameConversation = useCallback(
    async (id: string, newTitle: string) => {
      try {
        await chatApi.updateConversation(id, { title: newTitle });
        setConversations((prev) => prev.map((c) => (c.id === id ? { ...c, title: newTitle } : c)));
        if (conversationId === id) {
          setConversationTitle(newTitle);
        }
      } catch (error) {
        console.error("Failed to rename conversation:", error);
        toast.error("Error", { description: "Failed to rename conversation" });
      }
    },
    [conversationId]
  );

  const handleBulkDeleteConversations = useCallback(
    async (ids: string[]) => {
      try {
        const result = await chatApi.bulkDeleteConversations(ids);
        setConversations((prev) => prev.filter((c) => !ids.includes(c.id)));
        if (conversationId && ids.includes(conversationId)) {
          localStorage.removeItem(LAST_CONVERSATION_KEY);
          navigate("/workspace/chat");
        }
        toast.success("Conversations deleted", { description: result.message });
      } catch (error) {
        console.error("Failed to bulk delete conversations:", error);
        toast.error("Error", { description: "Failed to delete conversations" });
      }
    },
    [conversationId, navigate]
  );

  const handleDeleteAllConversations = useCallback(async () => {
    try {
      const result = await chatApi.deleteAllConversations();
      setConversations([]);
      localStorage.removeItem(LAST_CONVERSATION_KEY);
      navigate("/workspace/chat");
      toast.success("All conversations deleted", { description: result.message });
    } catch (error) {
      console.error("Failed to delete all conversations:", error);
      toast.error("Error", { description: "Failed to delete conversations" });
    }
  }, [navigate]);

  // ---------- Project handlers ----------

  const handleCreateProject = useCallback(async (name: string) => {
    try {
      const newProject = await projectsApi.createProject({ name });
      setProjects((prev) => [newProject, ...prev]);
      toast.success("Project created", { description: `Created "${name}"` });
    } catch (error) {
      console.error("Failed to create project:", error);
      toast.error("Error", { description: "Failed to create project" });
    }
  }, []);

  const handleUpdateProject = useCallback(async (id: string, data: { name?: string }) => {
    try {
      const updated = await projectsApi.updateProject(id, data);
      setProjects((prev) => prev.map((p) => (p.id === id ? updated : p)));
    } catch (error) {
      console.error("Failed to update project:", error);
      toast.error("Error", { description: "Failed to update project" });
    }
  }, []);

  const handleDeleteProject = useCallback(
    async (id: string) => {
      try {
        await projectsApi.deleteProject(id);
        setProjects((prev) => prev.filter((p) => p.id !== id));
        if (selectedProjectId === id) {
          setSelectedProjectId(null);
        }
        toast.success("Project deleted");
      } catch (error) {
        console.error("Failed to delete project:", error);
        toast.error("Error", { description: "Failed to delete project" });
      }
    },
    [selectedProjectId, setSelectedProjectId]
  );

  const handleMoveConversation = useCallback(
    async (convId: string, projectId: string | null) => {
      try {
        await projectsApi.moveConversationToProject(convId, projectId);
        setConversations((prev) =>
          prev.map((c) => (c.id === convId ? { ...c, project_id: projectId } : c))
        );
      } catch (error) {
        console.error("Failed to move conversation:", error);
        toast.error("Error", { description: "Failed to move conversation" });
      }
    },
    []
  );

  const handleDeleteProjectConversations = useCallback(
    async (projectId: string) => {
      try {
        const result = await projectsApi.deleteProjectConversations(projectId);
        setConversations((prev) => prev.filter((c) => c.project_id !== projectId));
        const currentConv = conversations.find((c) => c.id === conversationId);
        if (currentConv?.project_id === projectId) {
          localStorage.removeItem(LAST_CONVERSATION_KEY);
          navigate("/workspace/chat");
        }
        toast.success("Project conversations deleted", { description: result.message });
      } catch (error) {
        console.error("Failed to delete project conversations:", error);
        toast.error("Error", { description: "Failed to delete conversations" });
      }
    },
    [conversations, conversationId, navigate]
  );

  // ---------- Message handlers ----------

  const handleCopy = useCallback(
    async (content: string, id: string) => {
      try {
        await navigator.clipboard.writeText(content);
        setCopiedId(id);
        setTimeout(() => setCopiedId(null), 2000);
      } catch (err) {
        console.error("Failed to copy:", err);
      }
    },
    [setCopiedId]
  );

  const handleEdit = useCallback(
    (id: string) => {
      const message = messages.find((m) => m.id === id);
      if (message) {
        setEditingInput(message.content);
        setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, isEditing: true } : m)));
      }
    },
    [messages, setEditingInput]
  );

  const handleSaveEdit = useCallback(
    (id: string) => {
      if (!editingInput.trim()) return;
      setMessages((prev) =>
        prev.map((m) =>
          m.id === id ? { ...m, content: editingInput.trim(), isEditing: false } : m
        )
      );
      setEditingInput("");
    },
    [editingInput, setEditingInput]
  );

  const handleCancelEdit = useCallback(
    (id: string) => {
      setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, isEditing: false } : m)));
      setEditingInput("");
    },
    [setEditingInput]
  );

  const handleDelete = useCallback((id: string) => {
    setMessages((prev) => prev.filter((m) => m.id !== id));
  }, []);

  const handleFeedback = useCallback((id: string, type: "up" | "down") => {
    setMessages((prev) =>
      prev.map((m) =>
        m.id === id ? { ...m, feedback: m.feedback === type ? null : type } : m
      )
    );
  }, []);

  const handleViewPlanResults = useCallback(
    async (planId: number) => {
      try {
        const executions = await plansApi.getResults(planId);
        if (executions.length === 0) {
          toast.error("No execution results found");
          return;
        }
        const latest = executions[0];
        setSelectedPlanResult(latest);
        const planName = currentPlan?.id === planId ? currentPlan.name : `Plan #${planId}`;
        setSelectedPlanName(planName);
        setPlanResultModalOpen(true);
      } catch (error) {
        console.error("Failed to fetch plan results:", error);
        toast.error("Failed to load execution results");
      }
    },
    [currentPlan]
  );

  return {
    // Conversation state
    conversations,
    setConversations,
    conversationsLoading,
    conversationTitle,
    setConversationTitle,

    // Project state
    projects,
    selectedProjectId,
    setSelectedProjectId,

    // Message state
    messages,
    setMessages,
    isLoading,
    setIsLoading,
    streamingAssistantId,
    setStreamingAssistantId,

    // Plan state
    currentPlan,
    setCurrentPlan,
    planResultModalOpen,
    setPlanResultModalOpen,
    selectedPlanResult,
    setSelectedPlanResult,
    selectedPlanName,
    setSelectedPlanName,

    // Chat mode
    chatMode,
    setChatMode,

    // Loading state
    isLoadingConversation,

    // Computed values
    filteredMessages,
    groupedMessages,
    showEmptyState,

    // Handlers - Conversation CRUD
    handleSelectConversation,
    handleNewChat,
    handleDeleteConversation,
    handleRenameConversation,
    handleBulkDeleteConversations,
    handleDeleteAllConversations,

    // Handlers - Project CRUD
    handleCreateProject,
    handleUpdateProject,
    handleDeleteProject,
    handleMoveConversation,
    handleDeleteProjectConversations,

    // Handlers - Message operations
    handleCopy,
    handleEdit,
    handleSaveEdit,
    handleCancelEdit,
    handleDelete,
    handleFeedback,
    handleViewPlanResults,

    // Refs
    justCreatedConvRef,

    // Utilities
    generateTitle,
    initialMessages,
  };
}
