// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { memo } from "react";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuShortcut,
  ContextMenuTrigger,
} from "@/components/ui/context-menu";
import { Trash2, ArrowLeftRight, Pencil } from "lucide-react";

interface EdgeContextMenuProps {
  children: React.ReactNode;
  edgeId: string;
  isConditional?: boolean;
  onDelete: (id: string) => void;
  onReverse?: (id: string) => void;
  onEditCondition?: (id: string) => void;
}

const EdgeContextMenu = ({
  children,
  edgeId,
  isConditional = false,
  onDelete,
  onReverse,
  onEditCondition,
}: EdgeContextMenuProps) => {
  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>{children}</ContextMenuTrigger>
      <ContextMenuContent className="w-48">
        {isConditional && onEditCondition && (
          <>
            <ContextMenuItem
              onClick={() => onEditCondition(edgeId)}
              className="gap-2"
            >
              <Pencil size={14} />
              Edit Condition
            </ContextMenuItem>
            <ContextMenuSeparator />
          </>
        )}

        {onReverse && (
          <ContextMenuItem onClick={() => onReverse(edgeId)} className="gap-2">
            <ArrowLeftRight size={14} />
            Reverse Direction
          </ContextMenuItem>
        )}

        <ContextMenuSeparator />

        <ContextMenuItem
          onClick={() => onDelete(edgeId)}
          className="gap-2 text-destructive focus:text-destructive"
        >
          <Trash2 size={14} />
          Delete Connection
          <ContextMenuShortcut>Del</ContextMenuShortcut>
        </ContextMenuItem>
      </ContextMenuContent>
    </ContextMenu>
  );
};

export default memo(EdgeContextMenu);
