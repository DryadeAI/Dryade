// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
/**
 * Collapsible section for a single agent's execution.
 * Auto-collapses when agent completes, with delay for smooth UX.
 */
import { useEffect, useState, useRef } from "react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { ChevronRight, Loader2, CheckCircle2, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { CapabilityBadge } from "./CapabilityBadge";
import type { CapabilityStatus } from "./CapabilityBadge";

export type AgentStatus = "idle" | "running" | "complete" | "error";

interface AgentSectionProps {
  agent: string;
  status: AgentStatus;
  capabilityStatus: CapabilityStatus;
  capabilityDetails?: string;
  task?: string;
  children: React.ReactNode;
  className?: string;
}

export function AgentSection({
  agent,
  status,
  capabilityStatus,
  capabilityDetails,
  task,
  children,
  className,
}: AgentSectionProps) {
  // Auto-expand when running, auto-collapse when complete
  const [open, setOpen] = useState(status === "running");
  const hasRenderedContent = useRef(false);

  // Track when content has been rendered
  useEffect(() => {
    if (status === "running") {
      hasRenderedContent.current = true;
    }
  }, [status]);

  // Auto-collapse after completion with delay
  useEffect(() => {
    if (status === "complete" && hasRenderedContent.current) {
      // Delay collapse for smooth UX (see RESEARCH.md Pitfall 2)
      const timer = setTimeout(() => setOpen(false), 800);
      return () => clearTimeout(timer);
    }
  }, [status]);

  // Expand when status changes to running
  useEffect(() => {
    if (status === "running") {
      setOpen(true);
    }
  }, [status]);

  const statusIcon = {
    idle: null,
    running: <Loader2 className="h-4 w-4 animate-spin text-blue-500" />,
    complete: <CheckCircle2 className="h-4 w-4 text-green-500" />,
    error: <XCircle className="h-4 w-4 text-red-500" />,
  }[status];

  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      className={cn("border rounded-lg", className)}
    >
      <CollapsibleTrigger className="flex items-center gap-2 w-full p-3 hover:bg-muted/50 transition-colors">
        <ChevronRight
          className={cn(
            "h-4 w-4 transition-transform duration-200",
            open && "rotate-90"
          )}
        />
        <CapabilityBadge status={capabilityStatus} details={capabilityDetails} />
        <span className="font-medium flex-1 text-left">{agent}</span>
        {task && (
          <span className="text-xs text-muted-foreground truncate max-w-[200px]">
            {task}
          </span>
        )}
        {statusIcon}
      </CollapsibleTrigger>
      <CollapsibleContent
        className={cn(
          "overflow-hidden",
          "data-[state=open]:animate-collapsible-down",
          "data-[state=closed]:animate-collapsible-up"
        )}
      >
        <div className="p-3 pt-0 border-t">{children}</div>
      </CollapsibleContent>
    </Collapsible>
  );
}

export type { AgentSectionProps };
