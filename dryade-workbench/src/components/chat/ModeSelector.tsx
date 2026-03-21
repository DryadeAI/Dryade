// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { cn } from "@/lib/utils";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { MessageSquare, Brain } from "lucide-react";
import type { ChatMode } from "@/types/api";

interface ModeSelectorProps {
  value: ChatMode;
  onChange: (mode: ChatMode) => void;
  disabled?: boolean;
}

// Phase 85: Simplified to 2 modes
const modes: { id: ChatMode; label: string; icon: typeof MessageSquare; color: string; description: string }[] = [
  {
    id: "chat",
    label: "Chat",
    icon: MessageSquare,
    color: "text-muted-foreground",
    description: "Conversation with AI (auto-routes to agents when needed)",
  },
  {
    id: "planner",
    label: "Planner",
    icon: Brain,
    color: "text-purple-500",
    description: "AI-generated workflow plan with approval flow",
  },
];

const ModeSelector = ({ value, onChange, disabled = false }: ModeSelectorProps) => {
  return (
    <div
      className="flex gap-1 p-1 bg-secondary/50 rounded-lg"
      role="tablist"
      aria-label="Conversation mode"
    >
      {modes.map((mode) => {
        const isSelected = value === mode.id;
        const ModeIcon = mode.icon;

        return (
          <Tooltip key={mode.id}>
            <TooltipTrigger asChild>
              <button
                role="tab"
                aria-selected={isSelected}
                disabled={disabled}
                onClick={() => onChange(mode.id)}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-all",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  isSelected
                    ? "bg-background shadow-sm"
                    : "hover:bg-secondary",
                  disabled && "opacity-50 cursor-not-allowed"
                )}
              >
                <ModeIcon size={14} className={cn(isSelected ? mode.color : "text-muted-foreground")} />
                <span className={cn(isSelected ? "text-foreground" : "text-muted-foreground")}>
                  {mode.label}
                </span>
              </button>
            </TooltipTrigger>
            <TooltipContent>
              <p>{mode.description}</p>
            </TooltipContent>
          </Tooltip>
        );
      })}
    </div>
  );
};

export default ModeSelector;
