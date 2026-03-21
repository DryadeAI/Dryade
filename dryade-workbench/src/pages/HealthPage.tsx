// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { RefreshCw, Activity, Clock, Server, AlertTriangle, Database, Cpu, Globe, HardDrive, Radio } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { healthApi } from "@/services/api";
import type { DetailedHealth, ComponentStatus } from "@/types/api";
import { cn } from "@/lib/utils";
import { formatMs } from "@/lib/format";

const statusColors = {
  healthy: "bg-success",
  degraded: "bg-warning",
  unhealthy: "bg-destructive",
};

// statusText removed — now uses t("status.healthy") etc. via useTranslation

const formatUptime = (seconds: number) => {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${days}d ${hours}h ${minutes}m`;
};

const getComponentIcon = (name: string) => {
  const lower = name.toLowerCase();
  if (lower.includes("database") || lower.includes("postgres") || lower.includes("sql")) return Database;
  if (lower.includes("cache") || lower.includes("redis")) return HardDrive;
  if (lower.includes("api") || lower.includes("http") || lower.includes("service")) return Globe;
  if (lower.includes("worker") || lower.includes("queue")) return Cpu;
  if (lower.includes("stream") || lower.includes("event")) return Radio;
  return Server;
};

const DependencyCard = ({ component }: { component: ComponentStatus }) => {
  const { t } = useTranslation('health');
  const isHealthy = component.status === "healthy";
  const isDegraded = component.status === "degraded";
  const isUnhealthy = component.status === "unhealthy";
  const ComponentIcon = getComponentIcon(component.name);

  return (
    <div
      className={cn(
        "relative rounded-xl transition-all duration-300 h-full",
        !isHealthy && "glow-ring-animate",
      )}
      style={{
        "--ring-color": isDegraded
          ? "hsl(38 92% 50%)"
          : isUnhealthy
          ? "hsl(0 72% 51%)"
          : undefined,
      } as React.CSSProperties}
    >
      <Card
        className={cn(
          "border-border/50 transition-all duration-300 h-full",
          !isHealthy && "pulse-border",
          isDegraded && "hover:shadow-[0_0_20px_-5px_hsl(38_92%_50%/0.3)]",
          isUnhealthy && "hover:shadow-[0_0_20px_-5px_hsl(0_72%_51%/0.3)]",
          isHealthy && "hover:shadow-[0_0_20px_-5px_hsl(160_84%_39%/0.2)]",
        )}
        style={{
          "--pulse-color": isDegraded
            ? "hsl(38 92% 50% / 0.4)"
            : isUnhealthy
            ? "hsl(0 72% 51% / 0.4)"
            : undefined,
        } as React.CSSProperties}
      >
        <CardContent className="pt-4 pb-4">
          <div className="flex items-start justify-between">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <div
                  className={cn(
                    "p-1.5 rounded-lg",
                    isHealthy && "bg-success/10",
                    isDegraded && "bg-warning/10",
                    isUnhealthy && "bg-destructive/10",
                  )}
                >
                  <ComponentIcon
                    size={14}
                    className={cn(
                      isHealthy && "text-success",
                      isDegraded && "text-warning",
                      isUnhealthy && "text-destructive",
                    )}
                  />
                </div>
                <div className={cn("w-2 h-2 rounded-full", statusColors[component.status], !isHealthy && "motion-safe:animate-pulse")} />
                <span className="font-medium text-foreground">{component.name}</span>
              </div>
              {component.latency_ms !== undefined && (
                <p className="text-sm text-muted-foreground pl-8">
                  {t("latency", { value: formatMs(component.latency_ms) })}
                </p>
              )}
              {component.message && (
                <p className="text-sm text-muted-foreground pl-8">{component.message}</p>
              )}
            </div>
            <Badge
              variant="outline"
              className={cn(
                "text-xs capitalize",
                component.status === "healthy" && "border-success/50 text-success",
                component.status === "degraded" && "border-warning/50 text-warning",
                component.status === "unhealthy" && "border-destructive/50 text-destructive"
              )}
            >
              {t(`componentStatus.${component.status}`)}
            </Badge>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

const HealthPage = () => {
  const { t } = useTranslation('health');
  const [health, setHealth] = useState<DetailedHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());
  const [refreshCooldown, setRefreshCooldown] = useState(0);

  const fetchHealth = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await healthApi.getDetailedHealth();
      setHealth(data);
      setLastRefresh(new Date());
    } catch (err) {
      console.error("Failed to fetch health:", err);
      setError(err instanceof Error ? err.message : t("errorTitle"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHealth();
    const interval = setInterval(fetchHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (refreshCooldown > 0) {
      const timer = setTimeout(() => setRefreshCooldown(refreshCooldown - 1), 1000);
      return () => clearTimeout(timer);
    }
  }, [refreshCooldown]);

  const handleManualRefresh = () => {
    if (refreshCooldown === 0) {
      fetchHealth();
      setRefreshCooldown(10);
    }
  };

  const criticalComponents = health?.components.filter(c => c.category === "critical") || [];
  const importantComponents = health?.components.filter(c => c.category === "important") || [];
  const optionalComponents = health?.components.filter(c => c.category === "optional") || [];

  const degradedComponents = health?.components.filter(c => c.status !== "healthy") || [];

  const secondsSinceRefresh = Math.floor((Date.now() - lastRefresh.getTime()) / 1000);

  return (
    <div className="p-6 space-y-6" data-testid="health-container">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">{t("title")}</h1>
          <p className="text-muted-foreground">{t("subtitle")}</p>
        </div>
      </div>

      {/* Health Summary Card */}
      <Card className="border-border/50">
        <CardContent className="py-6">
          {loading && !health ? (
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <Skeleton className="w-4 h-4 rounded-full" />
                <Skeleton className="h-6 w-32" />
              </div>
              <Skeleton className="h-9 w-24" />
            </div>
          ) : health ? (
            <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
              <div className="flex flex-wrap items-center gap-6">
                {/* Status */}
                <div className="flex items-center gap-3">
                  <div className={cn("w-4 h-4 rounded-full motion-safe:animate-pulse", statusColors[health.status])} />
                  <span className="text-lg font-semibold text-foreground">
                    {t(`status.${health.status}`)}
                  </span>
                </div>

                {/* Uptime */}
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Clock aria-hidden="true" size={16} />
                  <span className="text-sm">{t("uptime", { time: formatUptime(health.uptime_seconds) })}</span>
                </div>

                {/* Version */}
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Server aria-hidden="true" size={16} />
                  <span className="text-sm">v{health.version}</span>
                </div>

                {/* Last Check */}
                <span className="text-sm text-muted-foreground">
                  {t("updatedAgo", { seconds: secondsSinceRefresh })}
                </span>
              </div>

              <Button
                variant="outline"
                size="sm"
                onClick={handleManualRefresh}
                disabled={refreshCooldown > 0}
                className="gap-2"
              >
                <RefreshCw aria-hidden="true" size={14} className={loading ? "motion-safe:animate-spin" : ""} />
                {refreshCooldown > 0 ? t("refreshCooldown", { seconds: refreshCooldown }) : t("refresh")}
              </Button>
            </div>
          ) : null}
        </CardContent>
      </Card>

      {/* Error State */}
      {error && !health && (
        <Card className="border-destructive/50 bg-destructive/10">
          <CardContent className="py-6 flex flex-col items-center gap-4">
            <AlertTriangle aria-hidden="true" className="w-8 h-8 text-destructive" />
            <div className="text-center space-y-1">
              <p className="font-semibold text-foreground">{t("errorTitle")}</p>
              <p className="text-sm text-muted-foreground">{error}</p>
            </div>
            <Button variant="outline" onClick={fetchHealth} className="gap-2">
              <RefreshCw aria-hidden="true" size={14} />
              {t("retry")}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Degraded/Unhealthy Banner */}
      {degradedComponents.length > 0 && (
        <Alert variant="destructive" className="border-warning/50 bg-warning/10">
          <AlertTriangle aria-hidden="true" className="h-4 w-4" />
          <AlertTitle className="text-warning">
            {degradedComponents.length > 1
              ? t("attentionBanner.plural", { count: degradedComponents.length })
              : t("attentionBanner.singular", { count: degradedComponents.length })}
          </AlertTitle>
          <AlertDescription className="text-warning/80">
            {degradedComponents.map(c => (
              <div key={c.name}>
                <strong>{c.name}:</strong> {c.message || c.status}
              </div>
            ))}
          </AlertDescription>
        </Alert>
      )}

      {/* Dependency Cards Grid */}
      {loading && !health ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(5)].map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      ) : (
        <div className="space-y-6">
          {/* Critical */}
          {criticalComponents.length > 0 && (
            <div className="space-y-3">
              <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wide">
                {t("categories.critical")}
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {criticalComponents.map(component => (
                  <DependencyCard key={component.name} component={component} />
                ))}
              </div>
            </div>
          )}

          {/* Important */}
          {importantComponents.length > 0 && (
            <div className="space-y-3">
              <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wide">
                {t("categories.important")}
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {importantComponents.map(component => (
                  <DependencyCard key={component.name} component={component} />
                ))}
              </div>
            </div>
          )}

          {/* Optional */}
          {optionalComponents.length > 0 && (
            <div className="space-y-3">
              <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wide">
                {t("categories.optional")}
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {optionalComponents.map(component => (
                  <DependencyCard key={component.name} component={component} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default HealthPage;
