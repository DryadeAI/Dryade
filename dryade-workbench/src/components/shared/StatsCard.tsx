// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// StatsCard - Statistic display card with trend indicator
// Based on COMPONENTS-4.md specification

import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import type { ReactNode } from "react";

interface StatsCardProps {
  title: string;
  value: number | string;
  icon?: ReactNode;
  trend?: {
    direction: "up" | "down" | "neutral";
    value: string;
    label?: string;
    isPositive?: boolean;  // semantic: up might be bad for errors
  };
  loading?: boolean;
  variant?: "default" | "success" | "warning" | "danger" | "hero" | "compact";
  accentColor?: "primary" | "secondary" | "tertiary";
  onClick?: () => void;
  className?: string;
  valueClassName?: string;
}

const variantStyles = {
  default: {
    icon: "text-primary bg-primary/10",
    trend: {
      up: "text-success",
      down: "text-destructive",
      neutral: "text-muted-foreground",
    },
  },
  success: {
    icon: "text-success bg-success/10",
    trend: {
      up: "text-success",
      down: "text-destructive",
      neutral: "text-muted-foreground",
    },
  },
  warning: {
    icon: "text-warning bg-warning/10",
    trend: {
      up: "text-success",
      down: "text-destructive",
      neutral: "text-muted-foreground",
    },
  },
  danger: {
    icon: "text-destructive bg-destructive/10",
    trend: {
      up: "text-destructive", // Inverted - up is bad
      down: "text-success", // Inverted - down is good
      neutral: "text-muted-foreground",
    },
  },
  hero: {
    icon: "text-primary bg-primary/10",
    trend: {
      up: "text-success",
      down: "text-destructive",
      neutral: "text-muted-foreground",
    },
  },
  compact: {
    icon: "text-primary bg-primary/10",
    trend: {
      up: "text-success",
      down: "text-destructive",
      neutral: "text-muted-foreground",
    },
  },
};

const accentColorStyles = {
  primary: "shadow-glow transition-shadow duration-normal hover:shadow-glow-lg",
  secondary: "shadow-glow-secondary transition-shadow duration-normal hover:shadow-glow-secondary/80",
  tertiary: "shadow-glow-tertiary transition-shadow duration-normal hover:shadow-glow-tertiary/80",
};

const TrendIcon = ({ direction }: { direction: "up" | "down" | "neutral" }) => {
  switch (direction) {
    case "up":
      return <TrendingUp className="w-3 h-3" />;
    case "down":
      return <TrendingDown className="w-3 h-3" />;
    default:
      return <Minus className="w-3 h-3" />;
  }
};

const StatsCard = ({
  title,
  value,
  icon,
  trend,
  loading = false,
  variant = "default",
  accentColor,
  onClick,
  className,
  valueClassName,
}: StatsCardProps) => {
  const styles = variantStyles[variant];

  // Determine size variant
  const isHero = variant === "hero";
  const isCompact = variant === "compact";

  // Apply sizing classes
  const cardPadding = isHero ? "p-6" : isCompact ? "p-3" : "p-4";
  const titleSize = isHero ? "text-base" : "text-sm";
  const valueSize = isHero ? "text-4xl" : isCompact ? "text-xl" : "text-2xl";
  const iconSize = isHero ? "w-12 h-12" : isCompact ? "w-8 h-8" : "w-10 h-10";

  // Apply accent color glow if specified
  const accentGlow = accentColor ? accentColorStyles[accentColor] : "";

  if (loading) {
    return (
      <Card className={cn("overflow-hidden", className)}>
        <CardContent className={cardPadding}>
          <div className="flex items-start justify-between">
            <div className="space-y-2 flex-1">
              <Skeleton className="h-4 w-24" />
              <Skeleton className={cn("w-32", isHero ? "h-10" : "h-8")} />
              <Skeleton className="h-3 w-20" />
            </div>
            <Skeleton className={cn("rounded-lg", iconSize)} />
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card
      className={cn(
        "overflow-hidden transition-all duration-normal",
        onClick && "cursor-pointer hover:scale-[1.02]",
        accentGlow,
        !accentGlow && "hover:shadow-md",
        className
      )}
      onClick={onClick}
    >
      <CardContent className={cardPadding}>
        <div className="flex items-start justify-between">
          <div className="space-y-1 flex-1 min-w-0">
            {/* Title */}
            <p className={cn("font-medium text-muted-foreground truncate", titleSize)}>
              {title}
            </p>

            {/* Value */}
            <p className={cn("font-bold text-foreground tabular-nums", valueSize, valueClassName)}>
              {value}
            </p>

            {/* Trend */}
            {trend && (
              <div
                className={cn(
                  "flex items-center gap-1 text-xs font-medium",
                  // Check isPositive prop for semantic coloring
                  trend.isPositive !== undefined
                    ? trend.isPositive
                      ? "text-success"
                      : "text-destructive"
                    : styles.trend[trend.direction]
                )}
              >
                <TrendIcon direction={trend.direction} />
                <span>{trend.value}</span>
                {trend.label && (
                  <span className="text-muted-foreground font-normal">
                    {trend.label}
                  </span>
                )}
              </div>
            )}
          </div>

          {/* Icon */}
          {icon && (
            <div
              className={cn(
                "flex items-center justify-center rounded-lg flex-shrink-0",
                iconSize,
                styles.icon
              )}
            >
              {icon}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
};

export default StatsCard;
