// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { ResizablePanel, CollapsiblePanel, SheetPanel } from "./panels";
import type { CollapsiblePanelIconAction } from "./panels";

// Header configuration
export interface PageHeaderConfig {
  title: string;
  subtitle?: string;
  icon?: React.ElementType;
  actions?: ReactNode;
}

// Panel configurations for different variants
export interface ResizablePanelConfig {
  variant: "resizable";
  position: "left" | "right";
  content: ReactNode;
  defaultWidth?: number;
  minWidth?: number;
  maxWidth?: number;
  onWidthChange?: (width: number) => void;
}

export interface CollapsiblePanelConfig {
  variant: "collapsible";
  position: "left" | "right";
  content: ReactNode;
  collapsed: boolean;
  onToggleCollapse: () => void;
  expandedWidth?: number;
  collapsedWidth?: number;
  iconActions?: CollapsiblePanelIconAction[];
}

export interface SheetPanelConfig {
  variant: "sheet";
  position: "left" | "right";
  content: ReactNode;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title?: string;
  width?: string;
}

export type PanelConfig =
  | ResizablePanelConfig
  | CollapsiblePanelConfig
  | SheetPanelConfig;

export interface PageLayoutProps {
  children: ReactNode;
  header?: PageHeaderConfig;
  panel?: PanelConfig;
  footer?: ReactNode;
  className?: string;
}

const PageLayout = ({
  children,
  header,
  panel,
  footer,
  className,
}: PageLayoutProps) => {
  // Render the appropriate panel component based on variant
  const renderPanel = () => {
    if (!panel) return null;

    switch (panel.variant) {
      case "resizable":
        return (
          <ResizablePanel
            position={panel.position}
            defaultWidth={panel.defaultWidth}
            minWidth={panel.minWidth}
            maxWidth={panel.maxWidth}
            onWidthChange={panel.onWidthChange}
          >
            {panel.content}
          </ResizablePanel>
        );

      case "collapsible":
        return (
          <CollapsiblePanel
            position={panel.position}
            collapsed={panel.collapsed}
            onToggleCollapse={panel.onToggleCollapse}
            expandedWidth={panel.expandedWidth}
            collapsedWidth={panel.collapsedWidth}
            iconActions={panel.iconActions}
          >
            {panel.content}
          </CollapsiblePanel>
        );

      case "sheet":
        return (
          <SheetPanel
            position={panel.position}
            open={panel.open}
            onOpenChange={panel.onOpenChange}
            title={panel.title}
            width={panel.width}
          >
            {panel.content}
          </SheetPanel>
        );

      default:
        return null;
    }
  };

  // For sheet panels, they render as a portal overlay, not in the flex layout
  const isSheetPanel = panel?.variant === "sheet";
  const panelPosition = panel?.position;

  return (
    <div className={cn("h-full flex flex-col", className)}>
      {/* Header */}
      {header && (
        <header className="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
          <div className="flex items-center gap-3">
            {header.icon && (
              <div className="p-2 rounded-lg bg-primary/10">
                <header.icon size={18} className="text-primary" />
              </div>
            )}
            <div>
              <h1 className="text-lg font-semibold text-foreground">
                {header.title}
              </h1>
              {header.subtitle && (
                <p className="text-xs text-muted-foreground">{header.subtitle}</p>
              )}
            </div>
          </div>
          {header.actions && (
            <div className="flex items-center gap-2">{header.actions}</div>
          )}
        </header>
      )}

      {/* Main content area with optional panel */}
      <div className="flex-1 flex min-h-0">
        {/* Left panel */}
        {!isSheetPanel && panelPosition === "left" && renderPanel()}

        {/* Main content */}
        <main className="flex-1 flex flex-col min-w-0">{children}</main>

        {/* Right panel */}
        {!isSheetPanel && panelPosition === "right" && renderPanel()}
      </div>

      {/* Sheet panel renders outside the flex layout */}
      {isSheetPanel && renderPanel()}

      {/* Footer */}
      {footer && (
        <footer className="border-t border-border shrink-0">{footer}</footer>
      )}
    </div>
  );
};

export default PageLayout;
