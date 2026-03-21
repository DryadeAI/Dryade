// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// ArtifactStatusBadge - Color-coded status indicator for factory artifacts
// Maps all 7 artifact lifecycle statuses to icon + color combinations

import { cn } from "@/lib/utils";
import {
  Settings,
  Clock,
  FileCode,
  FlaskConical,
  CheckCircle2,
  XCircle,
  Archive,
  RotateCcw,
  type LucideIcon,
} from "lucide-react";
import type { ArtifactStatus } from "@/services/api/factory";

interface StatusConfig {
  icon: LucideIcon;
  color: string;
  bgColor: string;
  label: string;
}

export const statusConfig: Record<ArtifactStatus, StatusConfig> = {
  configuring: {
    icon: Settings,
    color: "text-muted-foreground",
    bgColor: "bg-muted",
    label: "Configuring",
  },
  pending_approval: {
    icon: Clock,
    color: "text-amber-500",
    bgColor: "bg-amber-500/10",
    label: "Pending Approval",
  },
  scaffolded: {
    icon: FileCode,
    color: "text-blue-500",
    bgColor: "bg-blue-500/10",
    label: "Scaffolded",
  },
  testing: {
    icon: FlaskConical,
    color: "text-amber-500",
    bgColor: "bg-amber-500/10",
    label: "Testing",
  },
  active: {
    icon: CheckCircle2,
    color: "text-success",
    bgColor: "bg-success/10",
    label: "Active",
  },
  failed: {
    icon: XCircle,
    color: "text-destructive",
    bgColor: "bg-destructive/10",
    label: "Failed",
  },
  archived: {
    icon: Archive,
    color: "text-muted-foreground",
    bgColor: "bg-muted/50",
    label: "Archived",
  },
  rolled_back: {
    icon: RotateCcw,
    color: "text-orange-500",
    bgColor: "bg-orange-500/10",
    label: "Rolled Back",
  },
};

interface ArtifactStatusBadgeProps {
  status: ArtifactStatus;
  className?: string;
}

const ArtifactStatusBadge = ({ status, className }: ArtifactStatusBadgeProps) => {
  const config = statusConfig[status] ?? {
    icon: Settings,
    color: "text-muted-foreground",
    bgColor: "bg-muted",
    label: String(status ?? "Unknown"),
  };
  const Icon = config.icon;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
        config.bgColor,
        config.color,
        className
      )}
    >
      <Icon className="w-3.5 h-3.5" />
      {config.label}
    </span>
  );
};

export default ArtifactStatusBadge;
