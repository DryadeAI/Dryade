// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useRef, useEffect, useCallback, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { GripVertical } from "lucide-react";

export interface ResizablePanelProps {
  children: ReactNode;
  position: "left" | "right";
  defaultWidth?: number;
  minWidth?: number;
  maxWidth?: number;
  onWidthChange?: (width: number) => void;
  className?: string;
}

const ResizablePanel = ({
  children,
  position,
  defaultWidth = 320,
  minWidth = 240,
  maxWidth = 480,
  onWidthChange,
  className,
}: ResizablePanelProps) => {
  const [width, setWidth] = useState(defaultWidth);
  const [isResizing, setIsResizing] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  const handleResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizing(true);
  }, []);

  useEffect(() => {
    if (!isResizing) return;

    const handleMouseMove = (e: MouseEvent) => {
      const panelRect = panelRef.current?.getBoundingClientRect();
      if (!panelRect) return;

      let newWidth: number;
      if (position === "right") {
        newWidth = panelRect.right - e.clientX;
      } else {
        newWidth = e.clientX - panelRect.left;
      }

      const clampedWidth = Math.min(Math.max(newWidth, minWidth), maxWidth);
      setWidth(clampedWidth);
      onWidthChange?.(clampedWidth);
    };

    const handleMouseUp = () => {
      setIsResizing(false);
    };

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    document.body.style.cursor = "ew-resize";
    document.body.style.userSelect = "none";

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, [isResizing, minWidth, maxWidth, position, onWidthChange]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    const step = 10;
    if (e.key === "ArrowLeft") {
      const newWidth = position === "left" ? width - step : width + step;
      setWidth(Math.min(Math.max(newWidth, minWidth), maxWidth));
    } else if (e.key === "ArrowRight") {
      const newWidth = position === "left" ? width + step : width - step;
      setWidth(Math.min(Math.max(newWidth, minWidth), maxWidth));
    }
  };

  return (
    <div
      ref={panelRef}
      className={cn(
        "flex flex-col h-full relative border-border bg-card/50",
        position === "left" ? "border-r" : "border-l",
        className
      )}
      style={{ width }}
    >
      {/* Resize Handle */}
      <div
        onMouseDown={handleResizeStart}
        className={cn(
          "absolute top-0 bottom-0 w-1.5 cursor-ew-resize z-10 group",
          "hover:bg-primary/30 transition-colors",
          position === "left" ? "right-0" : "left-0",
          isResizing && "bg-primary/50"
        )}
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize panel"
        tabIndex={0}
        onKeyDown={handleKeyDown}
      >
        <div
          className={cn(
            "absolute top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity",
            position === "left" ? "right-0.5" : "left-0.5",
            isResizing && "opacity-100"
          )}
        >
          <GripVertical size={12} className="text-primary" />
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 flex flex-col min-h-0">{children}</div>
    </div>
  );
};

export default ResizablePanel;
