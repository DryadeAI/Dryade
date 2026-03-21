// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useMemo } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
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
  Plus,
  Folder,
  FolderOpen,
  ChevronRight,
  MoreHorizontal,
  Pencil,
  Trash2,
  Inbox,
} from "lucide-react";
import type { Project, Conversation } from "@/types/api";

interface ProjectsPanelProps {
  projects: Project[];
  conversations: Conversation[];
  selectedProjectId: string | null;
  selectedConversationId: string | null;
  onSelectProject: (id: string | null) => void;
  onSelectConversation: (id: string) => void;
  onCreateProject: (name: string) => Promise<void>;
  onUpdateProject: (id: string, data: { name?: string }) => Promise<void>;
  onDeleteProject: (id: string) => Promise<void>;
  onMoveConversation: (conversationId: string, projectId: string | null) => Promise<void>;
  isLoading?: boolean;
}

const ProjectsPanel = ({
  projects,
  conversations,
  selectedProjectId,
  selectedConversationId,
  onSelectProject,
  onSelectConversation,
  onCreateProject,
  onUpdateProject,
  onDeleteProject,
  onMoveConversation,
  isLoading = false,
}: ProjectsPanelProps) => {
  const [expandedProjects, setExpandedProjects] = useState<Set<string>>(new Set());
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [renameDialogOpen, setRenameDialogOpen] = useState(false);
  const [editingProject, setEditingProject] = useState<Project | null>(null);
  const [newProjectName, setNewProjectName] = useState("");

  // Group conversations by project
  const conversationsByProject = useMemo(() => {
    const grouped: Record<string | "none", Conversation[]> = { none: [] };

    projects.forEach((p) => {
      grouped[p.id] = [];
    });

    conversations.forEach((conv) => {
      if (conv.project_id && grouped[conv.project_id]) {
        grouped[conv.project_id].push(conv);
      } else {
        grouped.none.push(conv);
      }
    });

    return grouped;
  }, [projects, conversations]);

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
    setCreateDialogOpen(false);
  };

  const handleRenameProject = async () => {
    if (!editingProject || !newProjectName.trim()) return;
    await onUpdateProject(editingProject.id, { name: newProjectName.trim() });
    setNewProjectName("");
    setRenameDialogOpen(false);
    setEditingProject(null);
  };

  const openRenameDialog = (project: Project) => {
    setEditingProject(project);
    setNewProjectName(project.name);
    setRenameDialogOpen(true);
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="p-3 border-b border-border flex items-center justify-between">
        <span className="text-sm font-medium">Projects</span>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setCreateDialogOpen(true)}
          className="h-7 w-7 text-primary"
        >
          <Plus size={14} />
        </Button>
      </div>

      {/* Projects List */}
      <ScrollArea className="flex-1">
        <div className="p-2 space-y-1">
          {/* All Conversations (no project) */}
          <button
            onClick={() => onSelectProject(null)}
            className={cn(
              "w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-sm transition-colors",
              selectedProjectId === null
                ? "bg-primary/10 text-primary"
                : "hover:bg-muted text-foreground"
            )}
          >
            <Inbox size={14} />
            <span>All Conversations</span>
            <span className="ml-auto text-xs text-muted-foreground">
              {conversationsByProject.none?.length || 0}
            </span>
          </button>

          {/* Projects */}
          {projects.map((project) => {
            const isExpanded = expandedProjects.has(project.id);
            const projectConversations = conversationsByProject[project.id] || [];
            const isSelected = selectedProjectId === project.id;

            return (
              <Collapsible
                key={project.id}
                open={isExpanded}
                onOpenChange={() => toggleProject(project.id)}
              >
                <div className="group">
                  <div
                    className={cn(
                      "flex items-center gap-1 px-2 py-1.5 rounded-md transition-colors",
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
                      onClick={() => onSelectProject(project.id)}
                      className="flex-1 flex items-center gap-2 text-sm text-left"
                    >
                      {isExpanded ? (
                        <FolderOpen size={14} style={{ color: project.color || undefined }} />
                      ) : (
                        <Folder size={14} style={{ color: project.color || undefined }} />
                      )}
                      <span className={cn(isSelected && "text-primary font-medium")}>
                        {project.icon} {project.name}
                      </span>
                      <span className="ml-auto text-xs text-muted-foreground">
                        {projectConversations.length}
                      </span>
                    </button>

                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <button className="p-1 opacity-0 group-hover:opacity-100 hover:bg-muted rounded">
                          <MoreHorizontal size={12} />
                        </button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => openRenameDialog(project)}>
                          <Pencil size={14} />
                          Rename
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem
                          onClick={() => onDeleteProject(project.id)}
                          className="text-destructive focus:text-destructive"
                        >
                          <Trash2 size={14} />
                          Delete
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>

                  <CollapsibleContent>
                    <div className="ml-5 pl-2 border-l border-border space-y-0.5 mt-1">
                      {projectConversations.map((conv) => (
                        <button
                          key={conv.id}
                          onClick={() => onSelectConversation(conv.id)}
                          className={cn(
                            "w-full text-left px-2 py-1 rounded text-xs truncate transition-colors",
                            selectedConversationId === conv.id
                              ? "bg-primary/10 text-primary"
                              : "hover:bg-muted text-muted-foreground"
                          )}
                        >
                          {conv.title}
                        </button>
                      ))}
                      {projectConversations.length === 0 && (
                        <p className="px-2 py-1 text-xs text-muted-foreground italic">
                          No conversations
                        </p>
                      )}
                    </div>
                  </CollapsibleContent>
                </div>
              </Collapsible>
            );
          })}
        </div>
      </ScrollArea>

      {/* Create Project Dialog */}
      <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
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
            <Button variant="outline" onClick={() => setCreateDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreateProject} disabled={!newProjectName.trim()}>
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Rename Project Dialog */}
      <Dialog open={renameDialogOpen} onOpenChange={setRenameDialogOpen}>
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
            <Button variant="outline" onClick={() => setRenameDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleRenameProject} disabled={!newProjectName.trim()}>
              Rename
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default ProjectsPanel;
