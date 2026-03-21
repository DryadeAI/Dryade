// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// EmptyState - Unified empty state display with optional action, illustrations, and suggestions
// Supports all contexts: chat, workflow, agents, knowledge, files, search, etc.

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Inbox,
  MessageSquare,
  Workflow,
  Bot,
  BookOpen,
  FileText,
  Zap,
  Search,
  FolderOpen,
  Users,
  HelpCircle,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

type EmptyStateVariant =
  | "default"
  | "chat"
  | "workflow"
  | "agents"
  | "knowledge"
  | "files"
  | "search"
  | "folder"
  | "team";

export interface Suggestion {
  icon: LucideIcon;
  label: string;
  prompt: string;
}

interface EmptyStateProps {
  icon?: ReactNode;
  variant?: EmptyStateVariant;
  title: string;
  description?: string;
  action?: {
    label: string;
    onClick: () => void;
    variant?: "default" | "hero";
  };
  secondaryAction?: {
    label: string;
    onClick: () => void;
  };
  /** Quick-start suggestion cards (used by chat variant) */
  suggestions?: Suggestion[];
  /** Callback when a suggestion card is clicked */
  onSuggestionClick?: (prompt: string) => void;
  className?: string;
  size?: "sm" | "md" | "lg";
}

const variantConfig: Record<EmptyStateVariant, { icon: typeof Inbox; gradient: string }> = {
  default: { icon: Inbox, gradient: "from-muted/30 to-muted/10" },
  chat: { icon: MessageSquare, gradient: "from-primary/15 to-muted/10" },
  workflow: { icon: Workflow, gradient: "from-primary/12 to-muted/10" },
  agents: { icon: Bot, gradient: "from-primary/15 to-muted/10" },
  knowledge: { icon: BookOpen, gradient: "from-muted/30 to-muted/10" },
  files: { icon: FileText, gradient: "from-muted/30 to-muted/10" },
  search: { icon: Search, gradient: "from-muted/30 to-muted/10" },
  folder: { icon: FolderOpen, gradient: "from-muted/30 to-muted/10" },
  team: { icon: Users, gradient: "from-muted/30 to-muted/10" },
};

const sizeConfig = {
  sm: {
    container: "py-8 px-4",
    iconWrapper: "w-12 h-12 mb-3",
    iconSize: "w-6 h-6",
    title: "text-base font-medium",
    description: "text-sm max-w-xs mb-4",
  },
  md: {
    container: "py-12 px-4",
    iconWrapper: "w-16 h-16 mb-4",
    iconSize: "w-8 h-8",
    title: "text-lg font-semibold",
    description: "text-sm max-w-sm mb-6",
  },
  lg: {
    container: "py-16 px-6",
    iconWrapper: "w-20 h-20 mb-5",
    iconSize: "w-10 h-10",
    title: "text-xl font-semibold",
    description: "text-base max-w-md mb-8",
  },
};

const EmptyState = ({
  icon,
  variant = "default",
  title,
  description,
  action,
  secondaryAction,
  suggestions,
  onSuggestionClick,
  className,
  size = "md",
}: EmptyStateProps) => {
  const config = variantConfig[variant];
  const sizes = sizeConfig[size];
  const IconComponent = config.icon;

  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center",
        sizes.container,
        className
      )}
    >
      {/* Illustrated Icon with gradient background */}
      <div 
        className={cn(
          "relative flex items-center justify-center rounded-full bg-gradient-to-b",
          config.gradient,
          sizes.iconWrapper
        )}
      >
        {/* Decorative rings */}
        <div className="absolute inset-0 rounded-full border border-current opacity-10" />
        <div className="absolute -inset-2 rounded-full border border-current opacity-5" />
        
        {icon || <IconComponent className={cn(sizes.iconSize, "text-muted-foreground")} />}
        
        {/* Sparkle decoration for some variants */}
        {(variant === "workflow" || variant === "agents" || variant === "chat") && (
          <Zap
            className="absolute -top-1 -right-1 w-4 h-4 text-primary fill-primary/20"
            aria-hidden="true"
          />
        )}
      </div>

      {/* Title */}
      <h3 className={cn("text-foreground mb-1", sizes.title)}>{title}</h3>

      {/* Description */}
      {description && (
        <p className={cn("text-muted-foreground", sizes.description)}>
          {description}
        </p>
      )}

      {/* Actions */}
      {(action || secondaryAction) && (
        <div className="flex items-center gap-3">
          {secondaryAction && (
            <Button variant="outline" onClick={secondaryAction.onClick}>
              {secondaryAction.label}
            </Button>
          )}
          {action && (
            <Button
              variant={action.variant === "hero" ? "hero" : "default"}
              onClick={action.onClick}
            >
              {action.label}
            </Button>
          )}
        </div>
      )}

      {/* Suggestion Cards (chat-style quick actions) */}
      {suggestions && suggestions.length > 0 && onSuggestionClick && (
        <div className="grid grid-cols-2 gap-2 max-w-sm">
          {suggestions.map((suggestion) => (
            <Button
              key={suggestion.label}
              variant="outline"
              className="h-auto py-2 px-3 flex items-center gap-2 justify-start hover:bg-primary/5 hover:border-primary/30 transition-colors"
              onClick={() => onSuggestionClick(suggestion.prompt)}
            >
              <suggestion.icon className="w-4 h-4 text-primary shrink-0" aria-hidden="true" />
              <span className="text-xs font-medium">{suggestion.label}</span>
            </Button>
          ))}
        </div>
      )}
    </div>
  );
};

/** Default chat suggestions for the chat empty state */
export const chatSuggestions: Suggestion[] = [
  { icon: Workflow, label: "Create a workflow", prompt: "Help me create a new workflow" },
  { icon: Users, label: "Configure agents", prompt: "How do I configure an agent?" },
  { icon: Search, label: "Analyze data", prompt: "I want to analyze some data" },
  { icon: HelpCircle, label: "Ask a question", prompt: "What can you help me with?" },
];

export default EmptyState;
