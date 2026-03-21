// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { ReactNode } from "react";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuSub,
  ContextMenuSubContent,
  ContextMenuSubTrigger,
  ContextMenuTrigger,
} from "@/components/ui/context-menu";
import { Pencil, Trash2, FolderInput, Inbox, Folder } from "lucide-react";
import type { Project } from "@/types/api";

interface ConversationContextMenuProps {
  children: ReactNode;
  projects: Project[];
  currentProjectId: string | null;
  onRename: () => void;
  onDelete: () => void;
  onMoveToProject: (projectId: string | null) => void;
}

export const ConversationContextMenu = ({
  children,
  projects,
  currentProjectId,
  onRename,
  onDelete,
  onMoveToProject,
}: ConversationContextMenuProps) => {
  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>{children}</ContextMenuTrigger>
      <ContextMenuContent className="w-48">
        <ContextMenuItem onClick={onRename} className="gap-2">
          <Pencil size={14} />
          Rename
        </ContextMenuItem>

        <ContextMenuSub>
          <ContextMenuSubTrigger className="gap-2">
            <FolderInput size={14} />
            Move to Project
          </ContextMenuSubTrigger>
          <ContextMenuSubContent className="w-48">
            {/* Option to remove from project (move to ungrouped) */}
            <ContextMenuItem
              onClick={() => onMoveToProject(null)}
              disabled={currentProjectId === null}
              className="gap-2"
            >
              <Inbox size={14} />
              No Project
            </ContextMenuItem>

            {projects.length > 0 && <ContextMenuSeparator />}

            {/* List all projects */}
            {projects.map((project) => (
              <ContextMenuItem
                key={project.id}
                onClick={() => onMoveToProject(project.id)}
                disabled={currentProjectId === project.id}
                className="gap-2"
              >
                <Folder size={14} style={{ color: project.color || undefined }} />
                <span className="truncate">
                  {project.icon && `${project.icon} `}{project.name}
                </span>
              </ContextMenuItem>
            ))}
          </ContextMenuSubContent>
        </ContextMenuSub>

        <ContextMenuSeparator />

        <ContextMenuItem
          onClick={onDelete}
          className="gap-2 text-destructive focus:text-destructive"
        >
          <Trash2 size={14} />
          Delete
        </ContextMenuItem>
      </ContextMenuContent>
    </ContextMenu>
  );
};

export default ConversationContextMenu;
