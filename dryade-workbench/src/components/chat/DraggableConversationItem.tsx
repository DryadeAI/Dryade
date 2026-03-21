// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { ReactNode, useCallback } from "react";
import { useDraggable } from "@dnd-kit/core";
import { cn } from "@/lib/utils";

interface DraggableConversationItemProps {
  id: string;
  children: ReactNode;
  disabled?: boolean;
}

export const DraggableConversationItem = ({
  id,
  children,
  disabled = false,
}: DraggableConversationItemProps) => {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    isDragging,
  } = useDraggable({
    id,
    disabled,
  });

  const style = transform
    ? {
        transform: `translate3d(${transform.x}px, ${transform.y}px, 0)`,
      }
    : undefined;

  // Filter out pointer events on elements with data-no-drag attribute
  const filteredListeners = listeners
    ? Object.fromEntries(
        Object.entries(listeners).map(([key, handler]) => [
          key,
          (e: React.PointerEvent) => {
            // Check if the event target or any ancestor has data-no-drag
            const target = e.target as HTMLElement;
            if (target?.closest?.("[data-no-drag]")) return;
            (handler as (e: React.PointerEvent) => void)(e);
          },
        ])
      )
    : {};

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...(disabled ? {} : { ...attributes, ...filteredListeners })}
      className={cn(
        "relative cursor-grab active:cursor-grabbing touch-none",
        isDragging && "opacity-50 z-50"
      )}
    >
      {children}
    </div>
  );
};

export default DraggableConversationItem;
