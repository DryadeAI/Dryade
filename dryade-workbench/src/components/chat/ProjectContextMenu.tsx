// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { ReactNode } from "react";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from "@/components/ui/context-menu";
import { Pencil, Trash2, FileX2 } from "lucide-react";

interface ProjectContextMenuProps {
  children: ReactNode;
  onRename: () => void;
  onDeleteConversations: () => void;
  onDeleteProject: () => void;
  conversationCount: number;
}

export const ProjectContextMenu = ({
  children,
  onRename,
  onDeleteConversations,
  onDeleteProject,
  conversationCount,
}: ProjectContextMenuProps) => {
  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>{children}</ContextMenuTrigger>
      <ContextMenuContent className="w-52">
        <ContextMenuItem onClick={onRename} className="gap-2">
          <Pencil size={14} />
          Rename Project
        </ContextMenuItem>

        <ContextMenuSeparator />

        <ContextMenuItem
          onClick={onDeleteConversations}
          disabled={conversationCount === 0}
          className="gap-2 text-destructive focus:text-destructive"
        >
          <FileX2 size={14} />
          Delete All Conversations
          {conversationCount > 0 && (
            <span className="ml-auto text-xs opacity-60">({conversationCount})</span>
          )}
        </ContextMenuItem>

        <ContextMenuItem
          onClick={onDeleteProject}
          className="gap-2 text-destructive focus:text-destructive"
        >
          <Trash2 size={14} />
          Delete Project
        </ContextMenuItem>
      </ContextMenuContent>
    </ContextMenu>
  );
};

export default ProjectContextMenu;
