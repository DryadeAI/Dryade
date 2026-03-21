// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// UserRoleBadge - User role indicator
// Based on COMPONENTS-4.md specification

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Shield, User } from "lucide-react";

interface UserRoleBadgeProps {
  role: "admin" | "member";
  size?: "sm" | "md" | "lg";
  showIcon?: boolean;
  className?: string;
}

const roleConfig = {
  admin: {
    label: "Admin",
    icon: Shield,
    className: "bg-accent-secondary/10 text-accent-secondary border-accent-secondary/20",
  },
  member: {
    label: "Member",
    icon: User,
    className: "bg-muted text-muted-foreground border-muted",
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

const UserRoleBadge = ({
  role,
  size = "md",
  showIcon = true,
  className,
}: UserRoleBadgeProps) => {
  const config = roleConfig[role];
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

export default UserRoleBadge;
