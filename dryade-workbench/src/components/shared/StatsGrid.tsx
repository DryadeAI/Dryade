// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// StatsGrid - Responsive statistics grid
// Based on COMPONENTS-4.md specification

import { cn } from "@/lib/utils";
import StatsCard from "./StatsCard";
import type { ReactNode } from "react";

interface StatItem {
  label: string;
  value: string | number;
  icon?: ReactNode;
  trend?: {
    direction: "up" | "down" | "neutral";
    value: string;
    label?: string;
  };
  variant?: "default" | "success" | "warning" | "danger";
}

interface StatsGridProps {
  stats: StatItem[];
  columns?: 2 | 3 | 4;
  loading?: boolean;
  className?: string;
}

const columnClasses = {
  2: "grid-cols-1 sm:grid-cols-2",
  3: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3",
  4: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-4",
};

const StatsGrid = ({
  stats,
  columns = 4,
  loading = false,
  className,
}: StatsGridProps) => {
  return (
    <div className={cn("grid gap-4", columnClasses[columns], className)}>
      {stats.map((stat, index) => (
        <StatsCard
          key={index}
          title={stat.label}
          value={stat.value}
          icon={stat.icon}
          trend={stat.trend}
          variant={stat.variant}
          loading={loading}
        />
      ))}
    </div>
  );
};

export default StatsGrid;
