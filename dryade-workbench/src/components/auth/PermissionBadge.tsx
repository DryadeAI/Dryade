// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// PermissionBadge - Resource permission indicator
// Based on COMPONENTS-4.md specification

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Crown, Pencil, Eye } from "lucide-react";

interface PermissionBadgeProps {
  permission: "view" | "edit";
  isOwner?: boolean;
  size?: "sm" | "md" | "lg";
  showIcon?: boolean;
  className?: string;
}

const permissionConfig = {
  owner: {
    label: "Owner",
    icon: Crown,
    className: "bg-amber-500/10 text-amber-600 border-amber-500/20",
  },
  edit: {
    label: "Can Edit",
    icon: Pencil,
    className: "bg-success/10 text-success border-success/20",
  },
  view: {
    label: "View Only",
    icon: Eye,
    className: "bg-primary/10 text-primary border-primary/20",
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

const PermissionBadge = ({
  permission,
  isOwner = false,
  size = "md",
  showIcon = true,
  className,
}: PermissionBadgeProps) => {
  const key = isOwner ? "owner" : permission;
  const config = permissionConfig[key];
  const Icon = config.icon;

  return (
    <Badge
      variant="outline"
      className={cn(
        "gap-1 font-medium border",
        config.className,
        sizeClasses[size],
        className
      )}
    >
      {showIcon && <Icon size={iconSizes[size]} />}
      {config.label}
    </Badge>
  );
};

export default PermissionBadge;
