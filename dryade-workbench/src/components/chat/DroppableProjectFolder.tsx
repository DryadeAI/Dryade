// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { ReactNode } from "react";
import { useDroppable } from "@dnd-kit/core";
import { cn } from "@/lib/utils";

interface DroppableProjectFolderProps {
  id: string;
  children: ReactNode;
  disabled?: boolean;
}

export const DroppableProjectFolder = ({
  id,
  children,
  disabled = false,
}: DroppableProjectFolderProps) => {
  const { isOver, setNodeRef } = useDroppable({
    id,
    disabled,
  });

  return (
    <div
      ref={setNodeRef}
      className={cn(
        "transition-colors rounded-md",
        isOver && !disabled && "bg-primary/10 ring-1 ring-primary/30"
      )}
    >
      {children}
    </div>
  );
};

export default DroppableProjectFolder;
