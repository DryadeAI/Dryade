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
import {
  Play,
  Copy,
  Clipboard,
  Trash2,
  Settings2,
  FileOutput,
} from "lucide-react";

interface NodeContextMenuProps {
  children: React.ReactNode;
  nodeId: string;
  isRunning?: boolean;
  hasOutputs?: boolean;
  onRun: (id: string) => void;
  onDuplicate: (id: string) => void;
  onCopy: (id: string) => void;
  onDelete: (id: string) => void;
  onOpenProperties: (id: string) => void;
  onViewOutputs?: (id: string) => void;
}

const NodeContextMenu = ({
  children,
  nodeId,
  isRunning = false,
  hasOutputs = false,
  onRun,
  onDuplicate,
  onCopy,
  onDelete,
  onOpenProperties,
  onViewOutputs,
}: NodeContextMenuProps) => {
  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>{children}</ContextMenuTrigger>
      <ContextMenuContent className="w-48">
        <ContextMenuItem
          onClick={() => onRun(nodeId)}
          disabled={isRunning}
          className="gap-2"
        >
          <Play size={14} />
          Run Node
          <ContextMenuShortcut>Enter</ContextMenuShortcut>
        </ContextMenuItem>

        <ContextMenuSeparator />

        <ContextMenuItem onClick={() => onDuplicate(nodeId)} className="gap-2">
          <Copy size={14} />
          Duplicate
          <ContextMenuShortcut>⌘D</ContextMenuShortcut>
        </ContextMenuItem>

        <ContextMenuItem onClick={() => onCopy(nodeId)} className="gap-2">
          <Clipboard size={14} />
          Copy
          <ContextMenuShortcut>⌘C</ContextMenuShortcut>
        </ContextMenuItem>

        <ContextMenuSeparator />

        <ContextMenuItem
          onClick={() => onOpenProperties(nodeId)}
          className="gap-2"
        >
          <Settings2 size={14} />
          Properties
        </ContextMenuItem>

        {hasOutputs && onViewOutputs && (
          <ContextMenuItem
            onClick={() => onViewOutputs(nodeId)}
            className="gap-2"
          >
            <FileOutput size={14} />
            View Outputs
          </ContextMenuItem>
        )}

        <ContextMenuSeparator />

        <ContextMenuItem
          onClick={() => onDelete(nodeId)}
          className="gap-2 text-destructive focus:text-destructive"
        >
          <Trash2 size={14} />
          Delete
          <ContextMenuShortcut>Del</ContextMenuShortcut>
        </ContextMenuItem>
      </ContextMenuContent>
    </ContextMenu>
  );
};

export default memo(NodeContextMenu);
