// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { cn } from "@/lib/utils";
import { Activity, DollarSign, Clock, Database, TrendingUp, TrendingDown } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";

interface MetricCardData {
  label: string;
  value: string;
  change: string;
  trend: 'up' | 'down' | 'neutral';
  icon: typeof Activity;
  invertTrend?: boolean; // For metrics where down is good (e.g., cost, latency)
}

interface MetricsCardsProps {
  metrics?: MetricCardData[];
  isLoading?: boolean;
}

const defaultMetrics: MetricCardData[] = [
  { label: "Today's Requests", value: "1,234", change: "+12%", trend: "up", icon: Activity },
  { label: "Total Cost", value: "$12.45", change: "-5%", trend: "down", icon: DollarSign, invertTrend: true },
  { label: "Avg Latency", value: "89ms", change: "+3ms", trend: "up", icon: Clock, invertTrend: true },
  { label: "Cache Hit Rate", value: "67%", change: "+2%", trend: "up", icon: Database },
];

const MetricSkeleton = () => (
  <div className="glass-card p-5">
    <div className="flex items-center justify-between mb-3">
      <Skeleton className="h-10 w-10 rounded-lg" />
      <Skeleton className="h-4 w-12" />
    </div>
    <Skeleton className="h-8 w-24 mb-2" />
    <Skeleton className="h-4 w-32" />
  </div>
);

const MetricsCards = ({ metrics = defaultMetrics, isLoading = false }: MetricsCardsProps) => {
  if (isLoading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <MetricSkeleton key={i} />
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      {metrics.map((metric) => {
        // Determine if this trend is positive (green) or negative (red)
        const isPositiveTrend = metric.invertTrend
          ? metric.trend === 'down'
          : metric.trend === 'up';

        const TrendIcon = metric.trend === 'up' ? TrendingUp : TrendingDown;

        return (
          <div
            key={metric.label}
            className="glass-card p-5 hover:glow-primary-sm transition-shadow cursor-pointer"
          >
            <div className="flex items-center justify-between mb-3">
              <div className="p-2 rounded-lg bg-primary/10">
                <metric.icon size={18} className="text-primary" />
              </div>
              <div
                className={cn(
                  "flex items-center gap-1 text-xs font-medium",
                  isPositiveTrend ? "text-success" : "text-destructive"
                )}
              >
                <TrendIcon size={12} />
                {metric.change}
              </div>
            </div>
            <p className="text-2xl font-bold text-foreground mb-1 font-mono">
              {metric.value}
            </p>
            <p className="text-sm text-muted-foreground">{metric.label}</p>
          </div>
        );
      })}
    </div>
  );
};

export default MetricsCards;
