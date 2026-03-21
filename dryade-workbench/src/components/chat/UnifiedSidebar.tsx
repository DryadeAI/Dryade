// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useMemo, useEffect, useCallback, useRef } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  DndContext,
  DragOverlay,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import {
  Plus,
  Search,
  X,
  MessageSquare,
  GitBranch,
  Trash2,
  PanelRightClose,
  PanelRight,
  Folder,
  FolderOpen,
  ChevronRight,
  MoreVertical,
  Pencil,
  Inbox,
  FolderPlus,
  FileX2,
  Brain,
  FolderInput,
  Check,
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import type { Conversation, ChatMode, Project } from "@/types/api";
import { ConversationContextMenu } from "./ConversationContextMenu";
import { ProjectContextMenu } from "./ProjectContextMenu";
import { DraggableConversationItem } from "./DraggableConversationItem";
import { DroppableProjectFolder } from "./DroppableProjectFolder";
import { ConfirmDeleteDialog } from "./ConfirmDeleteDialog";

// Mode config for the 2 supported modes (Phase 85)
const modeConfig: Record<string, { icon: typeof MessageSquare; color: string; bgColor: string; label: string }> = {
  chat: { icon: MessageSquare, color: "text-muted-foreground", bgColor: "bg-muted/50", label: "Chat" },
  planner: { icon: Brain, color: "text-purple-500", bgColor: "bg-purple-500/10", label: "Planner" },
};

// Fallback for legacy modes (crew, flow, autonomous) - map to chat
const defaultModeConfig = { icon: MessageSquare, color: "text-muted-foreground", bgColor: "bg-muted/50", label: "Chat" };

// Get mode config with fallback for legacy modes
const getModeConfig = (mode: string) => modeConfig[mode] || defaultModeConfig;

// Group conversations by date
const groupConversationsByDate = (conversations: Conversation[]) => {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 24 * 60 * 60 * 1000);
  const thisWeek = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);

  const groups: { label: string; conversations: Conversation[] }[] = [
    { label: "Today", conversations: [] },
    { label: "Yesterday", conversations: [] },
    { label: "This Week", conversations: [] },
    { label: "Older", conversations: [] },
  ];

  conversations.forEach((conv) => {
    const updated = new Date(conv.updated_at);
    if (updated >= today) groups[0].conversations.push(conv);
    else if (updated >= yesterday) groups[1].conversations.push(conv);
    else if (updated >= thisWeek) groups[2].conversations.push(conv);
    else groups[3].conversations.push(conv);
  });

  return groups.filter((g) => g.conversations.length > 0);
};

interface UnifiedSidebarProps {
  projects: Project[];
  conversations: Conversation[];
  selectedProjectId: string | null;
  selectedConversationId: string | null;
  onSelectProject: (id: string | null) => void;
  onSelectConversation: (id: string) => void;
  onCreateProject: (name: string) => Promise<void>;
  onUpdateProject: (id: string, data: { name?: string }) => Promise<void>;
  onDeleteProject: (id: string) => Promise<void>;
  onDeleteConversation: (id: string) => void;
  onNewChat: () => void;
  onMoveConversation: (conversationId: string, projectId: string | null) => Promise<void>;
  onRenameConversation?: (id: string, newTitle: string) => Promise<void>;
  onBulkDeleteConversations?: (ids: string[]) => Promise<void>;
  onDeleteAllConversations?: () => Promise<void>;
  onDeleteProjectConversations?: (projectId: string) => Promise<void>;
  isLoading?: boolean;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

const UnifiedSidebar = ({
  projects,
  conversations,
  selectedProjectId,
  selectedConversationId,
  onSelectProject,
  onSelectConversation,
  onCreateProject,
  onUpdateProject,
  onDeleteProject,
  onDeleteConversation,
  onNewChat,
  onMoveConversation,
  onRenameConversation,
  onBulkDeleteConversations,
  onDeleteAllConversations,
  onDeleteProjectConversations,
  isLoading = false,
  collapsed = false,
  onToggleCollapse,
}: UnifiedSidebarProps) => {
  const [searchQuery, setSearchQuery] = useState("");
  const [hoveredConversationId, setHoveredConversationId] = useState<string | null>(null);
  const [expandedProjects, setExpandedProjects] = useState<Set<string>>(new Set());
  const [allConversationsExpanded, setAllConversationsExpanded] = useState(true);
  const [createProjectDialogOpen, setCreateProjectDialogOpen] = useState(false);
  const [renameProjectDialogOpen, setRenameProjectDialogOpen] = useState(false);
  const [editingProject, setEditingProject] = useState<Project | null>(null);
  const [newProjectName, setNewProjectName] = useState("");

  // Expose right panel width as CSS variable for background centering
  useEffect(() => {
    const width = collapsed ? "3rem" : "18rem";
    document.documentElement.style.setProperty("--right-panel-width", width);
    return () => { document.documentElement.style.removeProperty("--right-panel-width"); };
  }, [collapsed]);

  // Inline rename state for conversations
  const [renamingConversationId, setRenamingConversationId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

  // Delete confirmation dialogs
  const [deleteAllDialogOpen, setDeleteAllDialogOpen] = useState(false);
  const [deleteProjectConvsDialogOpen, setDeleteProjectConvsDialogOpen] = useState(false);
  const [deletingProjectId, setDeletingProjectId] = useState<string | null>(null);

  // Inline delete confirmation
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<string | null>(null);
  const confirmDeleteTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Drag state
  const [activeDragId, setActiveDragId] = useState<string | null>(null);

  // DnD sensors
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8,
      },
    }),
    useSensor(KeyboardSensor)
  );

  // Auto-expand project when a conversation in it is selected
  useEffect(() => {
    if (selectedConversationId) {
      const conv = conversations.find((c) => c.id === selectedConversationId);
      if (conv?.project_id && !expandedProjects.has(conv.project_id)) {
        setExpandedProjects((prev) => new Set([...prev, conv.project_id!]));
      }
    }
  }, [selectedConversationId, conversations]);

  // Filter conversations by search query
  const filteredConversations = useMemo(() => {
    if (!searchQuery.trim()) return conversations;
    const query = searchQuery.toLowerCase();
    return conversations.filter((c) => c.title?.toLowerCase().includes(query));
  }, [conversations, searchQuery]);

  // Group conversations by project
  const conversationsByProject = useMemo(() => {
    const grouped: Record<string | "none", Conversation[]> = { none: [] };

    (projects ?? []).forEach((p) => {
      grouped[p.id] = [];
    });

    (filteredConversations ?? []).forEach((conv) => {
      if (conv.project_id && grouped[conv.project_id]) {
        grouped[conv.project_id].push(conv);
      } else {
        grouped.none.push(conv);
      }
    });

    return grouped;
  }, [projects, filteredConversations]);

  const toggleProject = (id: string) => {
    setExpandedProjects((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleCreateProject = async () => {
    if (!newProjectName.trim()) return;
    await onCreateProject(newProjectName.trim());
    setNewProjectName("");
    setCreateProjectDialogOpen(false);
  };

  const handleRenameProject = async () => {
    if (!editingProject || !newProjectName.trim()) return;
    await onUpdateProject(editingProject.id, { name: newProjectName.trim() });
    setNewProjectName("");
    setRenameProjectDialogOpen(false);
    setEditingProject(null);
  };

  const openRenameDialog = (project: Project) => {
    setEditingProject(project);
    setNewProjectName(project.name);
    setRenameProjectDialogOpen(true);
  };

  // Conversation rename handlers
  const startRenamingConversation = useCallback((conv: Conversation) => {
    setRenamingConversationId(conv.id);
    setRenameValue(conv.title || "");
  }, []);

  const handleRenameConversation = useCallback(async () => {
    if (!renamingConversationId || !renameValue.trim() || !onRenameConversation) return;
    await onRenameConversation(renamingConversationId, renameValue.trim());
    setRenamingConversationId(null);
    setRenameValue("");
  }, [renamingConversationId, renameValue, onRenameConversation]);

  const cancelRenameConversation = useCallback(() => {
    setRenamingConversationId(null);
    setRenameValue("");
  }, []);

  // Delete project conversations handler
  const openDeleteProjectConvsDialog = useCallback((projectId: string) => {
    setDeletingProjectId(projectId);
    setDeleteProjectConvsDialogOpen(true);
  }, []);

  const handleDeleteProjectConvs = useCallback(async () => {
    if (!deletingProjectId || !onDeleteProjectConversations) return;
    await onDeleteProjectConversations(deletingProjectId);
    setDeletingProjectId(null);
  }, [deletingProjectId, onDeleteProjectConversations]);

  // DnD handlers
  const handleDragStart = useCallback((event: DragStartEvent) => {
    setActiveDragId(event.active.id as string);
  }, []);

  const handleDragEnd = useCallback(
    async (event: DragEndEvent) => {
      const { active, over } = event;
      setActiveDragId(null);

      if (!over) return;

      const conversationId = active.id as string;
      const targetId = over.id as string;

      // Find the conversation being dragged
      const conversation = conversations.find((c) => c.id === conversationId);
      if (!conversation) return;

      // Determine target project ID
      let targetProjectId: string | null = null;
      if (targetId === "droppable-none") {
        targetProjectId = null;
      } else if (targetId.startsWith("droppable-")) {
        targetProjectId = targetId.replace("droppable-", "");
      } else {
        return; // Invalid drop target
      }

      // Don't do anything if already in that project
      if (conversation.project_id === targetProjectId) return;

      await onMoveConversation(conversationId, targetProjectId);
    },
    [conversations, onMoveConversation]
  );

  // Find the conversation being dragged for DragOverlay
  const draggedConversation = activeDragId
    ? conversations.find((c) => c.id === activeDragId)
    : null;

  // Handle inline delete confirmation with auto-revert
  const startDeleteConfirmation = useCallback((convId: string) => {
    if (confirmDeleteTimeoutRef.current) clearTimeout(confirmDeleteTimeoutRef.current);
    setConfirmingDeleteId(convId);
    confirmDeleteTimeoutRef.current = setTimeout(() => {
      setConfirmingDeleteId(null);
    }, 3000);
  }, []);

  const cancelDeleteConfirmation = useCallback(() => {
    if (confirmDeleteTimeoutRef.current) clearTimeout(confirmDeleteTimeoutRef.current);
    setConfirmingDeleteId(null);
  }, []);

  const confirmDelete = useCallback((convId: string) => {
    if (confirmDeleteTimeoutRef.current) clearTimeout(confirmDeleteTimeoutRef.current);
    setConfirmingDeleteId(null);
    onDeleteConversation(convId);
  }, [onDeleteConversation]);

  // Render a conversation item with mode icon and metadata
  const renderConversationItem = (conv: Conversation) => {
    const config = getModeConfig(conv.mode);
    const ModeIcon = config.icon;
    const isSelected = conv.id === selectedConversationId;
    const isRenaming = conv.id === renamingConversationId;
    const isConfirmingDelete = conv.id === confirmingDeleteId;

    // Inline delete confirmation state
    if (isConfirmingDelete) {
      const confirmContent = (
        <div
          className="flex items-center gap-2 px-2 py-2 rounded-md bg-destructive/10 border border-destructive/30 w-full animate-in fade-in-50 duration-150"
          data-no-drag
        >
          <Trash2 size={14} className="text-destructive shrink-0" />
          <span className="text-sm text-destructive font-medium flex-1 truncate">Delete?</span>
          <div className="flex items-center gap-1 shrink-0">
            <Button
              variant="ghost"
              size="icon-sm"
              className="h-6 w-6 text-muted-foreground hover:text-foreground"
              onClick={(e) => {
                e.stopPropagation();
                cancelDeleteConfirmation();
              }}
            >
              <X size={14} />
            </Button>
            <Button
              variant="destructive"
              size="icon-sm"
              className="h-6 w-6"
              onClick={(e) => {
                e.stopPropagation();
                confirmDelete(conv.id);
              }}
            >
              <Check size={14} />
            </Button>
          </div>
        </div>
      );

      return (
        <DraggableConversationItem key={conv.id} id={conv.id}>
          {confirmContent}
        </DraggableConversationItem>
      );
    }

    const content = (
      <div
        onClick={() => !isRenaming && onSelectConversation(conv.id)}
        className={cn(
          "group/conv flex items-center gap-2.5 px-2 py-2 rounded-md cursor-pointer transition-all min-w-0 w-full relative",
          isSelected
            ? "bg-primary/10 border-l-[3px] border-l-primary border-y border-r border-y-primary/20 border-r-primary/20 pl-[calc(0.5rem-1px)]"
            : "hover:bg-muted/50 border border-transparent"
        )}
      >
        {/* Mode icon with background pill */}
        <div className={cn("p-1 rounded-md shrink-0", isSelected ? "bg-primary/15" : config.bgColor)}>
          <ModeIcon
            size={14}
            className={cn(isSelected ? "text-primary" : config.color)}
          />
        </div>

        <div className="flex-1 min-w-0">
          {isRenaming ? (
            <Input
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleRenameConversation();
                if (e.key === "Escape") cancelRenameConversation();
              }}
              onBlur={handleRenameConversation}
              autoFocus
              className="h-7 text-sm px-2 border-primary/30"
              onClick={(e) => e.stopPropagation()}
              onFocus={(e) => e.target.select()}
              data-no-drag
            />
          ) : (
            <>
              <p
                className={cn(
                  "text-sm truncate leading-tight",
                  isSelected ? "text-primary font-medium" : "text-foreground"
                )}
              >
                {conv.title || "New conversation"}
              </p>
              <p className="text-[10px] text-muted-foreground mt-0.5">
                {conv.message_count} msgs · {formatDistanceToNow(new Date(conv.updated_at), { addSuffix: true })}
              </p>
            </>
          )}
        </div>

        {/* Action menu */}
        {!isRenaming && (
          <div
            data-no-drag
            className="absolute right-1.5 top-1/2 -translate-y-1/2 opacity-0 group-hover/conv:opacity-100 transition-opacity"
          >
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/80 transition-colors"
                  onClick={(e) => e.stopPropagation()}
                >
                  <MoreVertical size={14} />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" side="right" sideOffset={4} className="w-44">
                {onRenameConversation && (
                  <DropdownMenuItem
                    className="gap-2 text-xs"
                    onClick={(e) => {
                      e.stopPropagation();
                      startRenamingConversation(conv);
                    }}
                  >
                    <Pencil size={13} />
                    Rename
                  </DropdownMenuItem>
                )}
                {projects.length > 0 && (
                  <>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      className="gap-2 text-xs"
                      disabled={conv.project_id === null}
                      onClick={(e) => {
                        e.stopPropagation();
                        onMoveConversation(conv.id, null);
                      }}
                    >
                      <Inbox size={13} />
                      Remove from project
                    </DropdownMenuItem>
                    {projects.map((p) => (
                      <DropdownMenuItem
                        key={p.id}
                        className="gap-2 text-xs"
                        disabled={conv.project_id === p.id}
                        onClick={(e) => {
                          e.stopPropagation();
                          onMoveConversation(conv.id, p.id);
                        }}
                      >
                        <Folder size={13} style={{ color: p.color || undefined }} />
                        <span className="truncate">{p.icon} {p.name}</span>
                      </DropdownMenuItem>
                    ))}
                  </>
                )}
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  className="gap-2 text-xs text-destructive focus:text-destructive"
                  onClick={(e) => {
                    e.stopPropagation();
                    startDeleteConfirmation(conv.id);
                  }}
                >
                  <Trash2 size={13} />
                  Delete
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        )}
      </div>
    );

    // Wrap in context menu and draggable
    return (
      <DraggableConversationItem key={conv.id} id={conv.id}>
        <ConversationContextMenu
          projects={projects}
          currentProjectId={conv.project_id || null}
          onRename={() => startRenamingConversation(conv)}
          onDelete={() => onDeleteConversation(conv.id)}
          onMoveToProject={(projectId) => onMoveConversation(conv.id, projectId)}
        >
          {content}
        </ConversationContextMenu>
      </DraggableConversationItem>
    );
  };

  // Render conversations with date grouping
  const renderGroupedConversations = (convs: Conversation[]) => {
    const groups = groupConversationsByDate(convs);
    
    if (groups.length === 0) return null;

    // If only one group, skip the header
    if (groups.length === 1) {
      return groups[0].conversations.map(renderConversationItem);
    }

    return groups.map((group) => (
      <div key={group.label} className="space-y-0.5">
        <h4 className="px-2 pt-2 pb-0.5 text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">
          {group.label}
        </h4>
        {group.conversations.map(renderConversationItem)}
      </div>
    ));
  };

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
    >
      <div className={cn(
        "h-full border-l border-border bg-card/50 hidden lg:flex flex-col overflow-hidden motion-safe:transition-[width] motion-safe:duration-300 ease-in-out",
        collapsed ? "w-12" : "w-72"
      )}>
        {/* Collapsed icon bar */}
        {collapsed && (
          <div className="flex flex-col items-center py-3 gap-2">
            <Button variant="ghost" size="icon" onClick={onToggleCollapse} className="h-8 w-8">
              <PanelRight size={16} />
            </Button>
            <Button variant="ghost" size="icon" onClick={onNewChat} className="h-8 w-8 text-primary">
              <Plus size={16} />
            </Button>
            <Button variant="ghost" size="icon" onClick={() => setCreateProjectDialogOpen(true)} className="h-8 w-8">
              <FolderPlus size={16} />
            </Button>
          </div>
        )}

        {/* Expanded content */}
        {!collapsed && (<>
        {/* Header with prominent New Chat */}
        <div className="p-3 border-b border-border space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">Workspace</span>
            {onToggleCollapse && (
              <Button
                variant="ghost"
                size="icon"
                onClick={onToggleCollapse}
                className="h-7 w-7"
                title="Collapse sidebar"
              >
                <PanelRightClose size={14} />
              </Button>
            )}
          </div>
          <Button
            onClick={onNewChat}
            className="w-full gap-2 bg-gradient-to-r from-primary to-accent hover:opacity-90"
            size="sm"
          >
            <Plus size={14} />
            New Chat
          </Button>
        </div>

        {/* Search */}
        <div className="p-2 border-b border-border">
          <div className="relative">
            <Search
              size={14}
              className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground"
            />
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search conversations..."
              className="pl-8 pr-7 h-8 text-sm"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery("")}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                <X size={12} />
              </button>
            )}
          </div>
        </div>

        {/* Content */}
        <ScrollArea className="flex-1 min-h-0">
          {isLoading ? (
            <div className="p-2 space-y-2">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : (
            <div className="p-2 space-y-1 w-full overflow-hidden">
              {/* All Conversations (ungrouped) */}
              <DroppableProjectFolder id="droppable-none">
                <Collapsible open={allConversationsExpanded} onOpenChange={setAllConversationsExpanded}>
                  <div className="group/section overflow-hidden">
                    <div
                      className={cn(
                        "flex items-center gap-1 px-2 py-1.5 rounded-md transition-colors min-w-0",
                        selectedProjectId === null ? "bg-primary/10" : "hover:bg-muted"
                      )}
                    >
                      <CollapsibleTrigger asChild>
                        <button className="p-0.5 hover:bg-muted rounded">
                          <ChevronRight
                            size={12}
                            className={cn(
                              "transition-transform",
                              allConversationsExpanded && "rotate-90"
                            )}
                          />
                        </button>
                      </CollapsibleTrigger>

                      <button
                        onClick={() => {
                          onSelectProject(null);
                          setAllConversationsExpanded(!allConversationsExpanded);
                        }}
                        className="flex-1 flex items-center gap-2 text-sm text-left min-w-0"
                      >
                        <Inbox size={14} className="shrink-0" />
                        <span className={cn("truncate", selectedProjectId === null && "text-primary font-medium")}>
                          All Conversations
                        </span>
                        <span className="ml-auto text-xs text-muted-foreground shrink-0">
                          {conversationsByProject.none?.length || 0}
                        </span>
                      </button>

                      {/* Delete All - always visible */}
                      {onDeleteAllConversations && conversations.length > 0 && (
                        <button
                          onClick={() => setDeleteAllDialogOpen(true)}
                          className="p-1 rounded transition-all text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                          title="Delete all conversations"
                        >
                          <Trash2 size={12} />
                        </button>
                      )}
                    </div>

                    <CollapsibleContent className="overflow-hidden">
                      <div className="ml-5 pl-2 border-l border-border space-y-0.5 mt-1 overflow-hidden">
                        {conversationsByProject.none.length > 0 ? (
                          renderGroupedConversations(conversationsByProject.none)
                        ) : (
                          <p className="px-2 py-1 text-xs text-muted-foreground italic">
                            {searchQuery ? "No matches" : "No ungrouped conversations"}
                          </p>
                        )}
                      </div>
                    </CollapsibleContent>
                  </div>
                </Collapsible>
              </DroppableProjectFolder>

              {/* Projects */}
              {projects.map((project) => {
                const isExpanded = expandedProjects.has(project.id);
                const projectConversations = conversationsByProject[project.id] || [];
                const isSelected = selectedProjectId === project.id;

                return (
                  <DroppableProjectFolder key={project.id} id={`droppable-${project.id}`}>
                    <ProjectContextMenu
                      onRename={() => openRenameDialog(project)}
                      onDeleteConversations={() => openDeleteProjectConvsDialog(project.id)}
                      onDeleteProject={() => onDeleteProject(project.id)}
                      conversationCount={projectConversations.length}
                    >
                      <Collapsible
                        open={isExpanded}
                        onOpenChange={() => toggleProject(project.id)}
                      >
                        <div className="group/section overflow-hidden">
                          <div
                            className={cn(
                              "flex items-center gap-1 px-2 py-1.5 rounded-md transition-colors min-w-0",
                              isSelected ? "bg-primary/10" : "hover:bg-muted"
                            )}
                          >
                            <CollapsibleTrigger asChild>
                              <button className="p-0.5 hover:bg-muted rounded">
                                <ChevronRight
                                  size={12}
                                  className={cn(
                                    "transition-transform",
                                    isExpanded && "rotate-90"
                                  )}
                                />
                              </button>
                            </CollapsibleTrigger>

                            <button
                              onClick={() => {
                                onSelectProject(project.id);
                                toggleProject(project.id);
                              }}
                              className="flex-1 flex items-center gap-2 text-sm text-left min-w-0"
                            >
                              {isExpanded ? (
                                <FolderOpen size={14} className="shrink-0" style={{ color: project.color || undefined }} />
                              ) : (
                                <Folder size={14} className="shrink-0" style={{ color: project.color || undefined }} />
                              )}
                              <span className={cn("truncate", isSelected && "text-primary font-medium")}>
                                {project.icon} {project.name}
                              </span>
                              <span className="ml-auto text-xs text-muted-foreground shrink-0">
                                {projectConversations.length}
                              </span>
                            </button>

                            {/* Delete project conversations - always visible */}
                            {onDeleteProjectConversations && projectConversations.length > 0 && (
                              <button
                                onClick={() => openDeleteProjectConvsDialog(project.id)}
                                className="p-1 rounded transition-all text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                                title="Delete all conversations in project"
                              >
                                <FileX2 size={12} />
                              </button>
                            )}

                            {/* Dropdown for project actions */}
                            <DropdownMenu>
                              <DropdownMenuTrigger asChild>
                                <button className="p-1 hover:bg-muted rounded transition-opacity">
                                  <MoreVertical size={12} />
                                </button>
                              </DropdownMenuTrigger>
                              <DropdownMenuContent align="end">
                                <DropdownMenuItem onClick={() => openRenameDialog(project)} className="gap-2">
                                  <Pencil size={14} />
                                  Rename
                                </DropdownMenuItem>
                                <DropdownMenuSeparator />
                                <DropdownMenuItem
                                  onClick={() => onDeleteProject(project.id)}
                                  className="gap-2 text-destructive focus:text-destructive"
                                >
                                  <Trash2 size={14} />
                                  Delete Project
                                </DropdownMenuItem>
                              </DropdownMenuContent>
                            </DropdownMenu>
                          </div>

                          <CollapsibleContent className="overflow-hidden">
                            <div className="ml-5 pl-2 border-l border-border space-y-0.5 mt-1 overflow-hidden">
                              {projectConversations.length > 0 ? (
                                renderGroupedConversations(projectConversations)
                              ) : (
                                <p className="px-2 py-1 text-xs text-muted-foreground italic">
                                  {searchQuery ? "No matches" : "No conversations"}
                                </p>
                              )}
                            </div>
                          </CollapsibleContent>
                        </div>
                      </Collapsible>
                    </ProjectContextMenu>
                  </DroppableProjectFolder>
                );
              })}
            </div>
          )}
        </ScrollArea>

        {/* Footer - New Project Button */}
        <div className="p-2 border-t border-border">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setCreateProjectDialogOpen(true)}
            className="w-full justify-start gap-2"
          >
            <FolderPlus size={14} />
            New Project
          </Button>
        </div>
        </>)}

        {/* Create Project Dialog */}
        <Dialog open={createProjectDialogOpen} onOpenChange={setCreateProjectDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create Project</DialogTitle>
              <DialogDescription>
                Create a new project to organize your conversations.
              </DialogDescription>
            </DialogHeader>
            <Input
              value={newProjectName}
              onChange={(e) => setNewProjectName(e.target.value)}
              placeholder="Project name"
              autoFocus
              onKeyDown={(e) => e.key === "Enter" && handleCreateProject()}
            />
            <DialogFooter>
              <Button variant="outline" onClick={() => setCreateProjectDialogOpen(false)}>
                Cancel
              </Button>
              <Button onClick={handleCreateProject} disabled={!newProjectName.trim()}>
                Create
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Rename Project Dialog */}
        <Dialog open={renameProjectDialogOpen} onOpenChange={setRenameProjectDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Rename Project</DialogTitle>
            </DialogHeader>
            <Input
              value={newProjectName}
              onChange={(e) => setNewProjectName(e.target.value)}
              placeholder="Project name"
              autoFocus
              onKeyDown={(e) => e.key === "Enter" && handleRenameProject()}
            />
            <DialogFooter>
              <Button variant="outline" onClick={() => setRenameProjectDialogOpen(false)}>
                Cancel
              </Button>
              <Button onClick={handleRenameProject} disabled={!newProjectName.trim()}>
                Rename
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Delete All Conversations Confirmation Dialog */}
        <ConfirmDeleteDialog
          open={deleteAllDialogOpen}
          onOpenChange={setDeleteAllDialogOpen}
          onConfirm={async () => {
            if (onDeleteAllConversations) {
              await onDeleteAllConversations();
            }
          }}
          title="Delete All Conversations"
          description="This action cannot be undone. All your conversations and their messages will be permanently deleted."
          confirmText="DELETE ALL"
          itemCount={conversations.length}
        />

        {/* Delete Project Conversations Confirmation Dialog */}
        <ConfirmDeleteDialog
          open={deleteProjectConvsDialogOpen}
          onOpenChange={setDeleteProjectConvsDialogOpen}
          onConfirm={handleDeleteProjectConvs}
          title="Delete Project Conversations"
          description="This action cannot be undone. All conversations in this project will be permanently deleted."
          confirmText="DELETE ALL"
          itemCount={
            deletingProjectId
              ? (conversationsByProject[deletingProjectId]?.length || 0)
              : 0
          }
        />

        {/* Drag Overlay - shows dragged item */}
        <DragOverlay>
          {draggedConversation && (
            <div className="bg-card border rounded-md shadow-lg p-2 opacity-90">
              <div className="flex items-center gap-2">
                <MessageSquare size={14} className="text-muted-foreground" />
                <span className="text-sm truncate max-w-48">
                  {draggedConversation.title || "New conversation"}
                </span>
              </div>
            </div>
          )}
        </DragOverlay>
      </div>
    </DndContext>
  );
};

export default UnifiedSidebar;
