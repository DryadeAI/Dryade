// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { type NodeType, type NodeStatus } from "@/types/workflow";
import {
  Upload,
  Cpu,
  Download,
  GitBranch,
  Bot,
  Wrench,
  Play,
  Route,
  CircleStop,
  ShieldCheck,
  LucideIcon,
} from "lucide-react";

interface NodeConfig {
  icon: LucideIcon;
  label: string;
  colorClass: string;
  bgClass: string;
  borderClass: string;
  description?: string;
}

export const nodeConfigs: Record<NodeType, NodeConfig> = {
  input: {
    icon: Upload,
    label: "Input",
    colorClass: "text-node-input",
    bgClass: "bg-node-input/10",
    borderClass: "border-node-input/30 hover:border-node-input/60",
    description: "Receives data or triggers workflow",
  },
  task: {
    icon: Cpu,
    label: "Task",
    colorClass: "text-node-process",
    bgClass: "bg-node-process/10",
    borderClass: "border-node-process/30 hover:border-node-process/60",
    description: "Transforms or processes data",
  },
  output: {
    icon: Download,
    label: "Output",
    colorClass: "text-node-output",
    bgClass: "bg-node-output/10",
    borderClass: "border-node-output/30 hover:border-node-output/60",
    description: "Returns results or triggers actions",
  },
  decision: {
    icon: GitBranch,
    label: "Decision",
    colorClass: "text-node-decision",
    bgClass: "bg-node-decision/10",
    borderClass: "border-node-decision/30 hover:border-node-decision/60",
    description: "Routes flow based on conditions",
  },
  agent: {
    icon: Bot,
    label: "Agent",
    colorClass: "text-primary",
    bgClass: "bg-primary/10",
    borderClass: "border-primary/30 hover:border-primary/60",
    description: "AI agent for autonomous tasks",
  },
  tool: {
    icon: Wrench,
    label: "Tool",
    colorClass: "text-cyan-500",
    bgClass: "bg-cyan-500/10",
    borderClass: "border-cyan-500/30 hover:border-cyan-500/60",
    description: "External tool or API integration",
  },
  start: {
    icon: Play,
    label: "Start",
    colorClass: "text-emerald-500",
    bgClass: "bg-emerald-500/10",
    borderClass: "border-emerald-500/30 hover:border-emerald-500/60",
    description: "Workflow entry point",
  },
  router: {
    icon: Route,
    label: "Router",
    colorClass: "text-amber-500",
    bgClass: "bg-amber-500/10",
    borderClass: "border-amber-500/30 hover:border-amber-500/60",
    description: "Routes flow based on conditions",
  },
  end: {
    icon: CircleStop,
    label: "End",
    colorClass: "text-rose-500",
    bgClass: "bg-rose-500/10",
    borderClass: "border-rose-500/30 hover:border-rose-500/60",
    description: "Workflow completion point",
  },
  approval: {
    icon: ShieldCheck,
    label: "Approval",
    colorClass: "text-amber-400",
    bgClass: "bg-amber-500/10",
    borderClass: "border-amber-500/30 hover:border-amber-500/60",
    description: "Human approval checkpoint",
  },
};

export const statusColors: Record<NodeStatus, string> = {
  idle: "bg-muted-foreground",
  pending: "bg-muted-foreground",
  running: "bg-primary animate-pulse",
  success: "bg-success",
  complete: "bg-success",
  error: "bg-destructive",
  skipped: "bg-muted-foreground",
  awaiting_approval: "bg-amber-400 animate-pulse",
};

export const getNodeConfig = (type: NodeType): NodeConfig => {
  return nodeConfigs[type] || nodeConfigs.task;
};
