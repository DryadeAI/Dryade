// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { memo } from "react";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuShortcut,
  ContextMenuSub,
  ContextMenuSubContent,
  ContextMenuSubTrigger,
  ContextMenuTrigger,
} from "@/components/ui/context-menu";
import {
  Play,
  Copy,
  Clipboard,
  Trash2,
  AlignHorizontalJustifyCenter,
  AlignVerticalJustifyCenter,
  AlignLeft,
  AlignRight,
  AlignStartVertical,
  AlignEndVertical,
} from "lucide-react";

interface SelectionContextMenuProps {
  children: React.ReactNode;
  selectedCount: number;
  onRunSelected: () => void;
  onDuplicateSelected: () => void;
  onCopySelected: () => void;
  onDeleteSelected: () => void;
  onAlignNodes: (
    alignment: "left" | "center" | "right" | "top" | "middle" | "bottom"
  ) => void;
}

const SelectionContextMenu = ({
  children,
  selectedCount,
  onRunSelected,
  onDuplicateSelected,
  onCopySelected,
  onDeleteSelected,
  onAlignNodes,
}: SelectionContextMenuProps) => {
  if (selectedCount < 2) {
    return <>{children}</>;
  }

  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>{children}</ContextMenuTrigger>
      <ContextMenuContent className="w-52">
        <ContextMenuItem onClick={onRunSelected} className="gap-2">
          <Play size={14} />
          Run {selectedCount} Nodes
        </ContextMenuItem>

        <ContextMenuSeparator />

        <ContextMenuItem onClick={onCopySelected} className="gap-2">
          <Clipboard size={14} />
          Copy All
          <ContextMenuShortcut>⌘C</ContextMenuShortcut>
        </ContextMenuItem>

        <ContextMenuItem onClick={onDuplicateSelected} className="gap-2">
          <Copy size={14} />
          Duplicate All
          <ContextMenuShortcut>⌘D</ContextMenuShortcut>
        </ContextMenuItem>

        <ContextMenuSeparator />

        <ContextMenuSub>
          <ContextMenuSubTrigger className="gap-2">
            <AlignHorizontalJustifyCenter size={14} />
            Align Horizontal
          </ContextMenuSubTrigger>
          <ContextMenuSubContent className="w-36">
            <ContextMenuItem
              onClick={() => onAlignNodes("left")}
              className="gap-2"
            >
              <AlignLeft size={14} />
              Left
            </ContextMenuItem>
            <ContextMenuItem
              onClick={() => onAlignNodes("center")}
              className="gap-2"
            >
              <AlignHorizontalJustifyCenter size={14} />
              Center
            </ContextMenuItem>
            <ContextMenuItem
              onClick={() => onAlignNodes("right")}
              className="gap-2"
            >
              <AlignRight size={14} />
              Right
            </ContextMenuItem>
          </ContextMenuSubContent>
        </ContextMenuSub>

        <ContextMenuSub>
          <ContextMenuSubTrigger className="gap-2">
            <AlignVerticalJustifyCenter size={14} />
            Align Vertical
          </ContextMenuSubTrigger>
          <ContextMenuSubContent className="w-36">
            <ContextMenuItem
              onClick={() => onAlignNodes("top")}
              className="gap-2"
            >
              <AlignStartVertical size={14} />
              Top
            </ContextMenuItem>
            <ContextMenuItem
              onClick={() => onAlignNodes("middle")}
              className="gap-2"
            >
              <AlignVerticalJustifyCenter size={14} />
              Middle
            </ContextMenuItem>
            <ContextMenuItem
              onClick={() => onAlignNodes("bottom")}
              className="gap-2"
            >
              <AlignEndVertical size={14} />
              Bottom
            </ContextMenuItem>
          </ContextMenuSubContent>
        </ContextMenuSub>

        <ContextMenuSeparator />

        <ContextMenuItem
          onClick={onDeleteSelected}
          className="gap-2 text-destructive focus:text-destructive"
        >
          <Trash2 size={14} />
          Delete {selectedCount} Nodes
          <ContextMenuShortcut>Del</ContextMenuShortcut>
        </ContextMenuItem>
      </ContextMenuContent>
    </ContextMenu>
  );
};

export default memo(SelectionContextMenu);
