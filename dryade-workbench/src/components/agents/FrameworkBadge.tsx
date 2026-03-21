// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { cn } from "@/lib/utils";
import { Ship, Link2, Box, Network, Plug, Cog } from "lucide-react";
import type { AgentFramework } from "@/types/api";

interface FrameworkBadgeProps {
  framework: AgentFramework;
  size?: "sm" | "md";
  showLabel?: boolean;
}

const frameworkConfig: Record<AgentFramework, { 
  label: string; 
  icon: typeof Ship;
  className: string;
}> = {
  crewai: {
    label: "CrewAI",
    icon: Ship,
    className: "bg-blue-500/15 text-blue-400 border-blue-500/30",
  },
  langchain: {
    label: "LangChain",
    icon: Link2,
    className: "bg-green-500/15 text-green-400 border-green-500/30",
  },
  adk: {
    label: "ADK",
    icon: Box,
    className: "bg-purple-500/15 text-purple-400 border-purple-500/30",
  },
  a2a: {
    label: "A2A",
    icon: Network,
    className: "bg-orange-500/15 text-orange-400 border-orange-500/30",
  },
  mcp: {
    label: "MCP",
    icon: Plug,
    className: "bg-teal-500/15 text-teal-400 border-teal-500/30",
  },
  custom: {
    label: "Custom",
    icon: Cog,
    className: "bg-gray-500/15 text-gray-400 border-gray-500/30",
  },
};

const FrameworkBadge = ({ framework, size = "sm", showLabel = true }: FrameworkBadgeProps) => {
  const config = frameworkConfig[framework];

  // Handle unknown frameworks gracefully
  if (!config) {
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1.5 rounded-full border font-medium",
          size === "sm" ? "px-2 py-0.5 text-xs" : "px-3 py-1 text-sm",
          "bg-gray-500/15 text-gray-400 border-gray-500/30"
        )}
      >
        <Box size={size === "sm" ? 12 : 14} />
        {showLabel && (framework || "Unknown")}
      </span>
    );
  }

  const Icon = config.icon;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border font-medium",
        size === "sm" ? "px-2 py-0.5 text-xs" : "px-3 py-1 text-sm",
        config.className
      )}
    >
      <Icon size={size === "sm" ? 12 : 14} />
      {showLabel && config.label}
    </span>
  );
};

export default FrameworkBadge;
