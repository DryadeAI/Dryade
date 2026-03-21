// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { cn } from "@/lib/utils";
import { Wrench, Loader2 } from "lucide-react";
import type { Agent } from "@/types/api";
import FrameworkBadge from "./FrameworkBadge";

interface AgentCardProps {
  agent: Agent;
  selected?: boolean;
  executing?: boolean;
  onClick?: () => void;
  onExecute?: () => void;
  // Legacy prop support
  isSelected?: boolean;
  isExecuting?: boolean;
}

const AgentCard = ({ 
  agent, 
  selected, 
  executing, 
  onClick, 
  onExecute,
  isSelected,
  isExecuting,
}: AgentCardProps) => {
  // Support both new and legacy props
  const isSelectedState = selected ?? isSelected;
  const isExecutingState = executing ?? isExecuting;
  return (
    <button
      onClick={onClick}
      role="gridcell"
      tabIndex={0}
      className={cn(
        "glass-card p-4 text-left w-full transition-all duration-200 relative group flex flex-col",
        "hover:scale-[1.02] hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        isSelectedState && "border-l-2 border-l-primary bg-primary/5",
        isExecutingState && "pointer-events-none"
      )}
    >
      {isExecutingState && (
        <div className="absolute inset-0 bg-background/60 backdrop-blur-sm flex items-center justify-center rounded-lg z-10">
          <Loader2 className="w-6 h-6 text-primary animate-spin" />
        </div>
      )}

      <div className="flex items-start justify-between gap-2 mb-1">
        {/* Role as primary (or name as fallback) */}
        <h3 className="font-semibold text-foreground text-base leading-tight">
          {agent.role || agent.name}
        </h3>
        <FrameworkBadge framework={agent.framework} size="sm" />
      </div>

      {/* Name as small identifier (only show if role exists) */}
      {agent.role && (
        <p className="text-[11px] text-muted-foreground/60 mb-2 font-mono">
          {agent.name}
        </p>
      )}

      {/* Goal as secondary description (or description as fallback) */}
      <p className="text-sm text-muted-foreground line-clamp-2 mb-3">
        {agent.goal || agent.description}
      </p>

      <div className="flex items-center gap-1.5 text-xs text-muted-foreground mt-auto">
        <Wrench size={12} />
        <span>{agent.tool_count} tools</span>
      </div>
    </button>
  );
};

export default AgentCard;
