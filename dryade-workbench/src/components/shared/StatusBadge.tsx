// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// StatusBadge - Colored status pill
// Based on COMPONENTS-4.md specification

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import {
  CheckCircle2,
  Clock,
  XCircle,
  AlertCircle,
  Play,
  Pause,
  Archive,
  FileText,
} from "lucide-react";

type StatusType =
  | "draft"
  | "published"
  | "archived"
  | "approved"
  | "executing"
  | "completed"
  | "failed"
  | "cancelled"
  | "pending"
  | "running"
  | "idle"
  | "error";

interface StatusBadgeProps {
  status: StatusType;
  size?: "sm" | "md" | "lg";
  animated?: boolean;
  showIcon?: boolean;
  className?: string;
}

const statusConfig: Record<
  StatusType,
  {
    label: string;
    icon: typeof Clock;
    variant: "default" | "secondary" | "destructive" | "outline";
    className: string;
    animationClass?: string;
  }
> = {
  draft: {
    label: "Draft",
    icon: FileText,
    variant: "outline",
    className: "bg-secondary text-muted-foreground border-border/30",
  },
  published: {
    label: "Published",
    icon: CheckCircle2,
    variant: "outline",
    className: "bg-success/15 text-success border-success/20",
  },
  archived: {
    label: "Archived",
    icon: Archive,
    variant: "outline",
    className: "bg-secondary text-muted-foreground border-border/30 line-through",
  },
  approved: {
    label: "Approved",
    icon: CheckCircle2,
    variant: "outline",
    className: "bg-success/15 text-success border-success/20",
  },
  executing: {
    label: "Executing",
    icon: Play,
    variant: "outline",
    className: "bg-warning/15 text-warning border-warning/20",
    animationClass: "animate-pulse",
  },
  completed: {
    label: "Completed",
    icon: CheckCircle2,
    variant: "outline",
    className: "bg-success/15 text-success border-success/20",
  },
  failed: {
    label: "Failed",
    icon: XCircle,
    variant: "outline",
    className: "bg-destructive/15 text-destructive border-destructive/20",
  },
  cancelled: {
    label: "Cancelled",
    icon: Pause,
    variant: "outline",
    className: "bg-secondary text-muted-foreground border-border/30 line-through",
  },
  pending: {
    label: "Pending",
    icon: Clock,
    variant: "outline",
    className: "bg-secondary text-muted-foreground border-border/30",
  },
  running: {
    label: "Running",
    icon: Play,
    variant: "outline",
    className: "bg-success/15 text-success border-success/20",
    animationClass: "animate-pulse",
  },
  idle: {
    label: "Idle",
    icon: Clock,
    variant: "outline",
    className: "bg-secondary text-muted-foreground border-border/30",
  },
  error: {
    label: "Error",
    icon: AlertCircle,
    variant: "outline",
    className: "bg-destructive/15 text-destructive border-destructive/20",
  },
};

const sizeClasses = {
  sm: "text-[10px] px-1.5 py-0.5 h-5",
  md: "text-xs px-2 py-0.5 h-6",
  lg: "text-sm px-2.5 py-1 h-7",
};

const iconSizes = {
  sm: 10,
  md: 12,
  lg: 14,
};

const StatusBadge = ({
  status,
  size = "md",
  animated = false,
  showIcon = true,
  className,
}: StatusBadgeProps) => {
  const config = statusConfig[status];
  const Icon = config.icon;
  const animationClass = animated && config.animationClass ? config.animationClass : "";

  return (
    <Badge
      variant="outline"
      className={cn(
        "gap-1 font-medium border",
        config.className,
        sizeClasses[size],
        animationClass,
        className
      )}
    >
      {showIcon && <Icon size={iconSizes[size]} />}
      {config.label}
    </Badge>
  );
};

export default StatusBadge;
