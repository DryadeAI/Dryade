// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { type ReactNode } from "react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";

export interface SheetPanelProps {
  children: ReactNode;
  position: "left" | "right";
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title?: string;
  width?: string;
  className?: string;
}

const SheetPanel = ({
  children,
  position,
  open,
  onOpenChange,
  title,
  width = "w-80",
  className,
}: SheetPanelProps) => {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side={position}
        className={`${width} p-0 ${className || ""}`}
      >
        {title && (
          <SheetHeader className="sr-only">
            <SheetTitle>{title}</SheetTitle>
          </SheetHeader>
        )}
        {children}
      </SheetContent>
    </Sheet>
  );
};

export default SheetPanel;
