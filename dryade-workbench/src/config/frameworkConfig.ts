// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
/**
 * Framework configuration for agent visualization
 * Provides consistent icons, colors, and labels across the UI
 */
import {
  Users,
  Link2,
  Cpu,
  Network,
  Server,
  Bot,
  Sparkles,
  Zap,
  Wrench,
  BookOpen,
  type LucideIcon,
} from "lucide-react";
import type { AgentFramework } from "@/types/api";

interface FrameworkStyle {
  icon: LucideIcon;
  label: string;
  color: string;        // Tailwind text color class
  bgColor: string;      // Tailwind background color class
  borderColor: string;  // Tailwind border color class
  hoverBg: string;      // Tailwind hover background
}

export const frameworkStyles: Record<AgentFramework | 'custom', FrameworkStyle> = {
  crewai: {
    icon: Users,
    label: "CrewAI",
    color: "text-violet-500",
    bgColor: "bg-violet-500/10",
    borderColor: "border-violet-500/30",
    hoverBg: "hover:bg-violet-500/20",
  },
  langchain: {
    icon: Link2,
    label: "LangChain",
    color: "text-emerald-500",
    bgColor: "bg-emerald-500/10",
    borderColor: "border-emerald-500/30",
    hoverBg: "hover:bg-emerald-500/20",
  },
  adk: {
    icon: Cpu,
    label: "ADK",
    color: "text-blue-500",
    bgColor: "bg-blue-500/10",
    borderColor: "border-blue-500/30",
    hoverBg: "hover:bg-blue-500/20",
  },
  a2a: {
    icon: Network,
    label: "A2A",
    color: "text-amber-500",
    bgColor: "bg-amber-500/10",
    borderColor: "border-amber-500/30",
    hoverBg: "hover:bg-amber-500/20",
  },
  mcp: {
    icon: Server,
    label: "MCP",
    color: "text-cyan-500",
    bgColor: "bg-cyan-500/10",
    borderColor: "border-cyan-500/30",
    hoverBg: "hover:bg-cyan-500/20",
  },
  custom: {
    icon: Bot,
    label: "Custom",
    color: "text-rose-500",
    bgColor: "bg-rose-500/10",
    borderColor: "border-rose-500/30",
    hoverBg: "hover:bg-rose-500/20",
  },
  mcp_function: {
    icon: Wrench,
    label: "MCP Function",
    color: "text-cyan-500",
    bgColor: "bg-cyan-500/10",
    borderColor: "border-cyan-500/30",
    hoverBg: "hover:bg-cyan-500/20",
  },
  mcp_server: {
    icon: Server,
    label: "MCP Server",
    color: "text-teal-500",
    bgColor: "bg-teal-500/10",
    borderColor: "border-teal-500/30",
    hoverBg: "hover:bg-teal-500/20",
  },
  skill: {
    icon: BookOpen,
    label: "Skill",
    color: "text-purple-500",
    bgColor: "bg-purple-500/10",
    borderColor: "border-purple-500/30",
    hoverBg: "hover:bg-purple-500/20",
  },
};

// Role-based icon mapping (if agent has specific role)
export const roleIcons: Record<string, LucideIcon> = {
  analyst: Sparkles,
  researcher: Link2,
  executor: Zap,
  planner: Cpu,
  reviewer: Users,
  default: Bot,
};

/**
 * Get framework style, with fallback to custom
 */
export function getFrameworkStyle(framework: string): FrameworkStyle {
  return frameworkStyles[framework as AgentFramework] || frameworkStyles.custom;
}

/**
 * Get icon for a role, with fallback to default
 */
export function getRoleIcon(role?: string): LucideIcon {
  if (!role) return roleIcons.default;
  const normalizedRole = role.toLowerCase();
  return roleIcons[normalizedRole] || roleIcons.default;
}
