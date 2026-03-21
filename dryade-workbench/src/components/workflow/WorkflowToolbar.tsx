// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { memo } from "react";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Toggle } from "@/components/ui/toggle";
import { Separator } from "@/components/ui/separator";
import {
  ZoomIn,
  ZoomOut,
  Maximize,
  Grid3X3,
  LayoutGrid,
  AlignStartHorizontal,
  AlignCenterHorizontal,
  AlignEndHorizontal,
  AlignStartVertical,
  AlignCenterVertical,
  AlignEndVertical,
  Trash2,
  Copy,
} from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
  DropdownMenuLabel,
} from "@/components/ui/dropdown-menu";

interface WorkflowToolbarProps {
  zoom: number;
  snapToGrid: boolean;
  selectedCount: number;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFitView: () => void;
  onResetZoom: () => void;
  onToggleSnap: () => void;
  onAutoLayout: () => void;
  onAlignNodes: (alignment: "left" | "center" | "right" | "top" | "middle" | "bottom") => void;
  onDeleteSelected: () => void;
  onDuplicateSelected: () => void;
}

const WorkflowToolbar = ({
  zoom,
  snapToGrid,
  selectedCount,
  onZoomIn,
  onZoomOut,
  onFitView,
  onResetZoom,
  onToggleSnap,
  onAutoLayout,
  onAlignNodes,
  onDeleteSelected,
  onDuplicateSelected,
}: WorkflowToolbarProps) => {
  const zoomPercentage = Math.round(zoom * 100);

  return (
    <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-10 flex items-center gap-1 px-2 py-1.5 rounded-xl bg-card/95 backdrop-blur-sm border border-border shadow-lg text-muted-foreground">
      {/* Zoom Controls */}
      <div className="flex items-center gap-0.5">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              className="h-7 w-7"
              onClick={onZoomOut}
            >
              <ZoomOut size={14} />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Zoom out</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 min-w-[52px] px-2 font-mono text-xs"
              onClick={onResetZoom}
            >
              {zoomPercentage}%
            </Button>
          </TooltipTrigger>
          <TooltipContent>Reset to 100% (⌘0)</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              className="h-7 w-7"
              onClick={onZoomIn}
            >
              <ZoomIn size={14} />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Zoom in</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              className="h-7 w-7"
              onClick={onFitView}
            >
              <Maximize size={14} />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Fit view (⌘1)</TooltipContent>
        </Tooltip>
      </div>

      <Separator orientation="vertical" className="h-5 mx-1" />

      {/* Grid & Layout */}
      <div className="flex items-center gap-0.5">
        <Tooltip>
          <TooltipTrigger asChild>
            <Toggle
              size="sm"
              className="h-7 w-7 p-0 data-[state=on]:bg-primary/20 data-[state=on]:text-primary"
              pressed={snapToGrid}
              onPressedChange={onToggleSnap}
            >
              <Grid3X3 size={14} />
            </Toggle>
          </TooltipTrigger>
          <TooltipContent>Snap to grid</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              className="h-7 w-7"
              onClick={onAutoLayout}
            >
              <LayoutGrid size={14} />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Auto-layout</TooltipContent>
        </Tooltip>
      </div>

      {/* Selection-based actions */}
      {selectedCount > 0 && (
        <>
          <Separator orientation="vertical" className="h-5 mx-1" />

          <div className="flex items-center gap-0.5">
            {/* Selection count badge */}
            <span className="px-2 py-0.5 text-[10px] font-medium bg-primary/20 text-primary rounded-md">
              {selectedCount} selected
            </span>

            {/* Alignment dropdown (only for multiple) */}
            {selectedCount > 1 && (
              <DropdownMenu>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="icon-sm" className="h-7 w-7">
                        <AlignCenterHorizontal size={14} />
                      </Button>
                    </DropdownMenuTrigger>
                  </TooltipTrigger>
                  <TooltipContent>Align nodes</TooltipContent>
                </Tooltip>
                <DropdownMenuContent align="center" side="top" className="min-w-[140px]">
                  <DropdownMenuLabel className="text-xs">Horizontal</DropdownMenuLabel>
                  <DropdownMenuItem onClick={() => onAlignNodes("left")}>
                    <AlignStartHorizontal size={14} className="mr-2" />
                    Align left
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => onAlignNodes("center")}>
                    <AlignCenterHorizontal size={14} className="mr-2" />
                    Align center
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => onAlignNodes("right")}>
                    <AlignEndHorizontal size={14} className="mr-2" />
                    Align right
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuLabel className="text-xs">Vertical</DropdownMenuLabel>
                  <DropdownMenuItem onClick={() => onAlignNodes("top")}>
                    <AlignStartVertical size={14} className="mr-2" />
                    Align top
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => onAlignNodes("middle")}>
                    <AlignCenterVertical size={14} className="mr-2" />
                    Align middle
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => onAlignNodes("bottom")}>
                    <AlignEndVertical size={14} className="mr-2" />
                    Align bottom
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            )}

            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="h-7 w-7"
                  onClick={onDuplicateSelected}
                >
                  <Copy size={14} />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Duplicate (⌘D)</TooltipContent>
            </Tooltip>

            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="h-7 w-7 text-destructive hover:text-destructive hover:bg-destructive/10"
                  onClick={onDeleteSelected}
                >
                  <Trash2 size={14} />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Delete (Del)</TooltipContent>
            </Tooltip>
          </div>
        </>
      )}
    </div>
  );
};

export default memo(WorkflowToolbar);
