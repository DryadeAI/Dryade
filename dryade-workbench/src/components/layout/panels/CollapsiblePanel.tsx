// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { type ReactNode, useEffect } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { PanelRight, PanelRightClose, PanelLeft, PanelLeftClose } from "lucide-react";

export interface CollapsiblePanelIconAction {
  icon: React.ElementType;
  label: string;
  onClick: () => void;
}

export interface CollapsiblePanelProps {
  children: ReactNode;
  position: "left" | "right";
  collapsed: boolean;
  onToggleCollapse: () => void;
  expandedWidth?: number;
  collapsedWidth?: number;
  iconActions?: CollapsiblePanelIconAction[];
  className?: string;
}

const CollapsiblePanel = ({
  children,
  position,
  collapsed,
  onToggleCollapse,
  expandedWidth = 288,
  collapsedWidth = 48,
  iconActions = [],
  className,
}: CollapsiblePanelProps) => {
  const ExpandIcon = position === "left" ? PanelLeft : PanelRight;
  const CollapseIcon = position === "left" ? PanelLeftClose : PanelRightClose;

  // Expose right panel width as CSS variable for background centering
  useEffect(() => {
    if (position === "right") {
      const width = collapsed ? `${collapsedWidth}px` : `${expandedWidth}px`;
      document.documentElement.style.setProperty("--right-panel-width", width);
    }
    return () => {
      if (position === "right") {
        document.documentElement.style.removeProperty("--right-panel-width");
      }
    };
  }, [position, collapsed, collapsedWidth, expandedWidth]);

  return (
    <div
      className={cn(
        "border-border bg-card/50 flex flex-col overflow-hidden",
        "motion-safe:transition-[width] motion-safe:duration-300 ease-in-out",
        position === "left" ? "border-r" : "border-l",
        className
      )}
      style={{ width: collapsed ? collapsedWidth : expandedWidth }}
    >
      {/* Toggle header */}
      <div className={cn(
        "shrink-0 flex items-center px-2 py-1.5",
        collapsed ? "justify-center py-3" : "border-b border-border/50",
        !collapsed && (position === "left" ? "justify-end" : "justify-start"),
      )}>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              onClick={onToggleCollapse}
              className={cn(collapsed ? "h-8 w-8" : "h-7 w-7 text-muted-foreground")}
            >
              {collapsed ? <ExpandIcon size={16} /> : <CollapseIcon size={14} />}
            </Button>
          </TooltipTrigger>
          <TooltipContent side={position === "left" ? "right" : "left"}>
            {collapsed ? "Expand panel" : "Collapse panel"}
          </TooltipContent>
        </Tooltip>
      </div>

      {/* Collapsed icon actions */}
      {collapsed && iconActions.length > 0 && (
        <div className="flex flex-col items-center gap-2">
          {iconActions.map((action, idx) => (
            <Tooltip key={idx}>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={action.onClick}
                  className="h-8 w-8"
                >
                  <action.icon size={16} />
                </Button>
              </TooltipTrigger>
              <TooltipContent side={position === "left" ? "right" : "left"}>
                {action.label}
              </TooltipContent>
            </Tooltip>
          ))}
        </div>
      )}

      {/* Panel content — hidden when collapsed via overflow */}
      <div className={cn(
        "flex-1 flex flex-col min-h-0 motion-safe:transition-opacity motion-safe:duration-200",
        collapsed ? "opacity-0 pointer-events-none" : "opacity-100"
      )}>
        {children}
      </div>
    </div>
  );
};

export default CollapsiblePanel;
