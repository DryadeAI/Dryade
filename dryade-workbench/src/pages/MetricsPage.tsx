// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useCallback, useMemo, useState, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { formatMs } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  AreaChart,
  Area,
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  PieChart,
  Pie,
  Cell,
} from "recharts";
import {
  Activity,
  Clock,
  Zap,
  Server,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Calendar,
  TrendingUp,
  Gauge,
  Download,
} from "lucide-react";
import { metricsApi, queueApi } from "@/services/api";
import EmptyState from "@/components/shared/EmptyState";
import type { QueueStatus } from "@/types/api";
import type { LatencyStats, ModeStats, RecentRequest } from "@/types/extended-api";

// ── Categorical colors for bar charts ─────────────────────────
const MODE_COLORS = [
  "hsl(var(--primary))",
  "hsl(200, 80%, 55%)",  // sky
  "hsl(260, 60%, 58%)",  // violet
  "hsl(35, 92%, 55%)",   // amber
  "hsl(160, 60%, 45%)",  // emerald
  "hsl(340, 65%, 55%)",  // rose
  "hsl(190, 70%, 50%)",  // cyan
  "hsl(280, 55%, 50%)",  // purple
];

// ── Reduced motion detection ──────────────────────────────────
const usePrefersReducedMotion = () => {
  const [reduced, setReduced] = useState(() =>
    typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const handler = (e: MediaQueryListEvent) => setReduced(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);
  return reduced;
};

// ── Animated counter hook ─────────────────────────────────────
const useAnimatedValue = (target: number, duration = 800) => {
  const reducedMotion = usePrefersReducedMotion();
  const [value, setValue] = useState(0);
  const startRef = useRef<number | null>(null);
  const prevRef = useRef(0);

  useEffect(() => {
    const from = prevRef.current;
    prevRef.current = target;

    if (reducedMotion) {
      setValue(target);
      return;
    }

    startRef.current = null;
    const animate = (ts: number) => {
      if (startRef.current === null) startRef.current = ts;
      const progress = Math.min((ts - startRef.current) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
      setValue(from + (target - from) * eased);
      if (progress < 1) requestAnimationFrame(animate);
    };
    requestAnimationFrame(animate);
  }, [target, duration, reducedMotion]);

  return Math.round(value);
};

// ── Animated metric card ──────────────────────────────────────
interface AnimatedMetricProps {
  label: string;
  value: number;
  suffix?: string;
  icon: React.ElementType;
  color: string;
  gradient: string;
  delay?: number;
}

const AnimatedMetricCard = ({ label, value, suffix = "ms", icon: Icon, color, gradient, delay = 0 }: AnimatedMetricProps) => {
  const { t } = useTranslation('metrics');
  const prefersReducedMotion = usePrefersReducedMotion();
  const animatedValue = useAnimatedValue(value);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setVisible(true), delay);
    return () => clearTimeout(timer);
  }, [delay]);

  const effectiveVisible = prefersReducedMotion || visible;

  const getStatusRing = (ms: number) => {
    if (ms < 200) return "ring-success/30";
    if (ms < 500) return "ring-warning/30";
    return "ring-destructive/30";
  };


  return (
    <div
      role="region"
      aria-label={label}
      className={cn(
        "relative overflow-hidden rounded-xl border bg-card p-5 transition-all duration-500 shimmer-overlay",
        "hover:shadow-lg hover:-translate-y-0.5",
        "motion-reduce:transition-none motion-reduce:translate-y-0 motion-reduce:opacity-100",
        "ring-2",
        getStatusRing(value),
        effectiveVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
      )}
    >
      {/* Background gradient glow */}
      <div className={cn("absolute -top-12 -right-12 w-32 h-32 rounded-full opacity-20 blur-2xl", gradient)} />

      <div className="relative flex items-start justify-between mb-4">
        <div className={cn("p-2.5 rounded-xl", gradient)}>
          <Icon className="w-5 h-5 text-primary-foreground" />
        </div>
        {/* Live pulse indicator */}
        <div className="flex items-center gap-1.5">
          <div className={cn("w-2 h-2 rounded-full animate-pulse", color)} aria-hidden="true" />
          <span className="text-[10px] text-muted-foreground uppercase tracking-wider font-medium">{t('live')}</span>
        </div>
      </div>

      <div className="relative">
        <p className="text-3xl font-bold text-foreground font-mono tabular-nums tracking-tight">
          {animatedValue}<span className="text-lg text-muted-foreground ml-0.5">{suffix}</span>
        </p>
        <p className="text-sm text-muted-foreground mt-1">{label}</p>
      </div>

      {/* Bottom accent bar */}
      <div className={cn("absolute bottom-0 left-0 right-0 h-0.5", gradient)} />
    </div>
  );
};

// ── Glowing Donut Chart (Alien_pixels-inspired) ──────────────
const DONUT_COLORS = [
  { key: "success", color: "hsl(var(--success))", labelKey: "donut.success" },
  { key: "error", color: "hsl(var(--destructive))", labelKey: "donut.errors" },
];

const GlowingDonutCard = ({ recentRequests }: { recentRequests: RecentRequest[] }) => {
  const { t } = useTranslation('metrics');
  const prefersReducedMotion = usePrefersReducedMotion();
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setVisible(true), 300);
    return () => clearTimeout(t);
  }, []);

  const effectiveVisible = prefersReducedMotion || visible;

  const successCount = recentRequests.filter(r => r.status === "success").length;
  const errorCount = recentRequests.filter(r => r.status !== "success").length;
  const total = recentRequests.length;
  const animatedTotal = useAnimatedValue(total);

  const donutData = [
    { name: t('donut.success'), value: successCount, color: "hsl(var(--success))" },
    { name: t('donut.errors'), value: errorCount, color: "hsl(var(--destructive))" },
  ].filter(d => d.value > 0);

  return (
    <Card
      className={cn(
        "relative overflow-hidden border-primary/20 p-6 transition-all duration-300 flex flex-col",
        "hover:border-primary/40 hover:shadow-glow",
        effectiveVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-6"
      )}
    >
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-48 h-24 bg-primary/10 rounded-full blur-3xl pointer-events-none" />

      <h3 className="relative text-lg font-semibold text-foreground mb-1 flex items-center gap-2">
        <Activity className="w-5 h-5 text-primary" />
        {t('donut.title')}
      </h3>
      <p className="text-sm text-muted-foreground mb-4">{t('donut.description')}</p>

      <div className="relative flex justify-center flex-1">
        <ResponsiveContainer width="100%" height={280}>
          <PieChart>
            <Pie
              data={donutData}
              cx="50%"
              cy="50%"
              innerRadius={60}
              outerRadius={85}
              paddingAngle={3}
              dataKey="value"
              strokeWidth={0}
            >
              {donutData.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.color} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{
                backgroundColor: "hsl(var(--card))",
                border: "1px solid hsl(var(--border))",
                borderRadius: "8px",
              }}
              formatter={(value: number, name: string) => [
                `${value} (${total > 0 ? ((value / total) * 100).toFixed(1) : 0}%)`,
                name,
              ]}
            />
          </PieChart>
        </ResponsiveContainer>

        {/* Central counter */}
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="text-center">
            <p className="text-3xl font-bold text-foreground font-mono tabular-nums">
              {animatedTotal.toLocaleString()}
            </p>
            <p className="text-xs text-muted-foreground uppercase tracking-wider">{t('total')}</p>
          </div>
        </div>
      </div>

      {/* Legend */}
      <div className="flex items-center justify-center gap-5 mt-3">
        {DONUT_COLORS.map(c => {
          const count = c.key === "success" ? successCount : errorCount;
          return (
            <div key={c.key} className="flex items-center gap-1.5">
              <div
                className="w-2.5 h-2.5 rounded-full"
                style={{ backgroundColor: c.color }}
              />
              <span className="text-xs text-muted-foreground">{t(c.labelKey)} ({count})</span>
            </div>
          );
        })}
      </div>
    </Card>
  );
};

// ── Radar metric card (Alien_pixels-inspired) ────────────────
const radarColors = [
  { nameKey: "radar.latency", key: "latency", color: "hsl(var(--success))" },
  { nameKey: "radar.requests", key: "requests", color: "hsl(var(--info))" },
  { nameKey: "radar.errorRate", key: "errorRate", color: "hsl(var(--destructive))" },
];

const RadarMetricCard = ({ modeStats }: { modeStats: ModeStats[] }) => {
  const { t } = useTranslation('metrics');
  const prefersReducedMotion = usePrefersReducedMotion();
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setVisible(true), 200);
    return () => clearTimeout(t);
  }, []);

  const effectiveVisible = prefersReducedMotion || visible;

  const totalRequests = modeStats.reduce((s, m) => s + m.request_count, 0);
  const avgLatency = modeStats.length > 0
    ? Math.round(modeStats.reduce((s, m) => s + m.avg_latency_ms, 0) / modeStats.length)
    : 0;
  const animatedTotal = useAnimatedValue(totalRequests);
  const animatedAvg = useAnimatedValue(avgLatency);

  // Normalize data for radar (0-100 scale)
  const maxLatency = Math.max(...modeStats.map(m => m.avg_latency_ms), 1);
  const maxRequests = Math.max(...modeStats.map(m => m.request_count), 1);
  const maxErrors = Math.max(...modeStats.map(m => Math.round((1 - m.success_rate) * m.request_count)), 1);

  const radarData = modeStats.map(m => ({
    mode: m.mode,
    latency: Math.round((m.avg_latency_ms / maxLatency) * 100),
    requests: Math.round((m.request_count / maxRequests) * 100),
    errorRate: Math.round((Math.round((1 - m.success_rate) * m.request_count)) / maxErrors * 100),
  }));

  // Breakdown sorted by request count
  const sorted = [...modeStats].sort((a, b) => b.request_count - a.request_count);

  return (
    <Card
      className={cn(
        "relative overflow-hidden border-primary/20 p-6 transition-all duration-300 flex flex-col",
        "hover:border-primary/40 hover:shadow-glow",
        effectiveVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-6"
      )}
    >
      {/* Ambient glow */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-64 h-32 bg-primary/10 rounded-full blur-3xl pointer-events-none" />

      <div className="relative grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-6">
        {/* Left: Radar chart */}
        <div>
          <h3 className="text-lg font-semibold text-foreground mb-1 flex items-center gap-2">
            <Activity className="w-5 h-5 text-primary" />
            {t('radar.title')}
          </h3>
          <p className="text-sm text-muted-foreground mb-4">{t('radar.description')}</p>

          <div className="flex justify-center">
            <ResponsiveContainer width="100%" height={280}>
              <RadarChart cx="50%" cy="50%" outerRadius="75%" data={radarData}>
                <PolarGrid stroke="hsl(var(--border))" />
                <PolarAngleAxis
                  dataKey="mode"
                  tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11, fontWeight: 500 }}
                />
                <PolarRadiusAxis
                  angle={30}
                  domain={[0, 100]}
                  tick={false}
                  axisLine={false}
                />
                <Radar
                  name={t('radar.latency')}
                  dataKey="latency"
                  stroke="hsl(var(--success))"
                  strokeWidth={2}
                  fill="hsl(var(--success))"
                  fillOpacity={0.15}
                  dot={{ r: 3, fill: "hsl(var(--success))", strokeWidth: 0 }}
                />
                <Radar
                  name={t('radar.requests')}
                  dataKey="requests"
                  stroke="hsl(var(--info))"
                  strokeWidth={2}
                  strokeDasharray="6 3"
                  fill="hsl(var(--info))"
                  fillOpacity={0.1}
                  dot={{ r: 3, fill: "hsl(var(--info))", strokeWidth: 0 }}
                />
                <Radar
                  name={t('donut.errors')}
                  dataKey="errorRate"
                  stroke="hsl(var(--destructive))"
                  strokeWidth={1.5}
                  strokeDasharray="3 3"
                  fill="hsl(var(--destructive))"
                  fillOpacity={0.05}
                  dot={{ r: 2, fill: "hsl(var(--destructive))", strokeWidth: 0 }}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "hsl(var(--card))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: "8px",
                  }}
                  formatter={(value: number, name: string) => [`${value}%`, name]}
                />
              </RadarChart>
            </ResponsiveContainer>
          </div>

          {/* Legend */}
          <div className="flex items-center justify-center gap-5 mt-2">
            {radarColors.map(c => (
              <div key={c.key} className="flex items-center gap-1.5">
                <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: c.color }} />
                <span className="text-xs text-muted-foreground">{t(c.nameKey)}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Right: KPIs + Breakdown */}
        <div className="flex flex-col justify-between">
          {/* Summary KPIs */}
          <div className="grid grid-cols-2 gap-3 mb-5">
            <div className="rounded-xl bg-foreground/5 border border-border p-4">
              <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">{t('radar.totalRequests')}</p>
              <p className="text-2xl font-bold text-foreground font-mono tabular-nums">{animatedTotal.toLocaleString()}</p>
            </div>
            <div className="rounded-xl bg-foreground/5 border border-border p-4">
              <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">{t('radar.avgLatency')}</p>
              <p className="text-2xl font-bold text-foreground font-mono tabular-nums">{animatedAvg}<span className="text-sm text-muted-foreground ml-0.5">ms</span></p>
            </div>
          </div>

          {/* Mode Breakdown */}
          <div className="space-y-2.5">
            <p className="text-xs text-muted-foreground uppercase tracking-wider font-medium">{t('radar.topModes')}</p>
            {sorted.slice(0, 4).map((m, i) => {
              const pct = maxRequests > 0 ? (m.request_count / maxRequests) * 100 : 0;
              return (
                <div key={m.mode} className="group">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm text-foreground/80 capitalize">{m.mode}</span>
                    <span className="text-xs text-muted-foreground font-mono">{m.request_count.toLocaleString()}</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-foreground/5 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-primary to-primary/70 transition-all duration-1000 ease-out motion-reduce:transition-none"
                      style={{
                        width: effectiveVisible ? `${pct}%` : "0%",
                        transitionDelay: `${400 + i * 150}ms`,
                      }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </Card>
  );
};

const getLatencyColor = (ms: number): string => {
  if (ms < 200) return "text-success";
  if (ms < 500) return "text-warning";
  return "text-destructive";
};

type TabType = "overview" | "queue";
type DateRange = "1h" | "24h";

const MetricsPage = () => {
  const { t } = useTranslation('metrics');
  const [latencyStats, setLatencyStats] = useState<LatencyStats | null>(null);
  const [queueStatus, setQueueStatus] = useState<QueueStatus | null>(null);
  const [modeStats, setModeStats] = useState<ModeStats[]>([]);
  const [recentRequests, setRecentRequests] = useState<RecentRequest[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedRequest, setSelectedRequest] = useState<RecentRequest | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date());
  const [activeTab, setActiveTab] = useState<TabType>("overview");
  const [dateRange, setDateRange] = useState<DateRange>("24h");
  const [autoRefresh, setAutoRefresh] = useState(true);

  // Recent Requests filters & pagination
  const [statusFilter, setStatusFilter] = useState<"all" | "success" | "error">("all");
  const [modeFilter, setModeFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const PAGE_SIZE = 15;

  const availableModes = useMemo(() => {
    const modes = new Set(recentRequests.map(r => r.mode));
    return Array.from(modes).sort();
  }, [recentRequests]);

  const filteredRequests = useMemo(() => {
    let filtered = recentRequests;
    if (statusFilter !== "all") {
      filtered = filtered.filter(r => r.status === statusFilter);
    }
    if (modeFilter !== "all") {
      filtered = filtered.filter(r => r.mode === modeFilter);
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      filtered = filtered.filter(r =>
        r.id.toLowerCase().includes(q) ||
        r.mode.toLowerCase().includes(q) ||
        (r.error_message && r.error_message.toLowerCase().includes(q))
      );
    }
    return filtered;
  }, [recentRequests, statusFilter, modeFilter, searchQuery]);

  const totalPages = Math.max(1, Math.ceil(filteredRequests.length / PAGE_SIZE));
  const safePage = Math.min(currentPage, totalPages);
  const paginatedRequests = useMemo(() => {
    const start = (safePage - 1) * PAGE_SIZE;
    return filteredRequests.slice(start, start + PAGE_SIZE);
  }, [filteredRequests, safePage, PAGE_SIZE]);

  const maxLatencyInPage = useMemo(() => Math.max(...filteredRequests.map(r => r.latency_ms), 1), [filteredRequests]);

  const requestSummary = useMemo(() => {
    const total = filteredRequests.length;
    const successCount = filteredRequests.filter(r => r.status === "success").length;
    const errorCount = total - successCount;
    const avgLatency = total > 0 ? filteredRequests.reduce((sum, r) => sum + r.latency_ms, 0) / total : 0;
    return { total, successCount, errorCount, successRate: total > 0 ? (successCount / total) * 100 : 0, avgLatency };
  }, [filteredRequests]);

  // Reset page when filters change
  useEffect(() => {
    setCurrentPage(1);
  }, [statusFilter, modeFilter, searchQuery]);

  const recentLimit = useMemo(() => {
    switch (dateRange) {
      case "1h":
        return 50;
      case "24h":
      default:
        return 200;
    }
  }, [dateRange]);

  const handleExportCSV = useCallback(() => {
    if (filteredRequests.length === 0) return;
    const headers = ["ID", "Timestamp", "Mode", "Latency (ms)", "Tokens", "Status", "Error"];
    const rows = filteredRequests.map((r) => [
      r.id,
      new Date(r.timestamp).toISOString(),
      r.mode,
      r.latency_ms,
      r.tokens,
      r.status,
      r.error_message || "",
    ]);
    const csv = [headers, ...rows].map((row) => row.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `dryade-metrics-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [filteredRequests]);

  const loadData = useCallback(
    async (withLoading: boolean) => {
      if (withLoading) setIsLoading(true);

      try {
        const [latency, byMode, recent, queue] = await Promise.all([
          metricsApi.getLatency(),
          metricsApi.getLatencyByMode(),
          metricsApi.getLatencyRecent(recentLimit),
          queueApi.getStatus(),
        ]);

        setLatencyStats(latency);
        setModeStats(byMode);
        setRecentRequests(recent);
        setQueueStatus(queue);
        setError(null);
      } catch (err) {
        const message = err instanceof Error ? err.message : t('error.failedToLoad');
        setError(message);
        console.error("Failed to load metrics:", err);
      } finally {
        if (withLoading) setIsLoading(false);
        setLastUpdated(new Date());
      }
    },
    [recentLimit]
  );

  useEffect(() => {
    let isActive = true;

    const refresh = async (withLoading: boolean) => {
      if (!isActive) return;
      await loadData(withLoading);
    };

    void refresh(true);
    const intervalId = autoRefresh
      ? window.setInterval(() => void refresh(false), 30000)
      : null;

    return () => {
      isActive = false;
      if (intervalId) window.clearInterval(intervalId);
    };
  }, [loadData, autoRefresh]);

  const handleRefresh = () => {
    void loadData(true);
  };

  const trendData = useMemo(() => {
    if (recentRequests.length === 0) return [];

    const sorted = [...recentRequests].sort(
      (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
    );

    const start = new Date(sorted[0].timestamp).getTime();
    const end = new Date(sorted[sorted.length - 1].timestamp).getTime();
    const bucketCount = Math.min(20, Math.max(6, sorted.length));
    const spanMs = Math.max(1, end - start);
    const bucketMs = spanMs / bucketCount;

    const buckets = Array.from({ length: bucketCount }, (_, i) => ({
      startMs: start + i * bucketMs,
      latencySum: 0,
      count: 0,
    }));

    for (const request of sorted) {
      const ts = new Date(request.timestamp).getTime();
      const idx = Math.min(bucketCount - 1, Math.floor((ts - start) / bucketMs));
      buckets[idx].latencySum += request.latency_ms;
      buckets[idx].count += 1;
    }

    return buckets.map((b) => {
      const label = new Date(Math.round(b.startMs)).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      });
      return {
        time: label,
        latency: b.count > 0 ? Math.round((b.latencySum / b.count) * 10) / 10 : 0,
        requests: b.count,
      };
    });
  }, [recentRequests]);

  const queueLevel = useMemo(() => {
    if (!queueStatus) return null;
    if (queueStatus.queued === 0 && queueStatus.active < queueStatus.max_concurrent * 0.8) return "healthy";
    if (queueStatus.queued < queueStatus.max_queue_size * 0.5) return "busy";
    return "overloaded";
  }, [queueStatus]);

  if (isLoading) {
    return (
      <div className="h-full overflow-auto p-6">
        <div className="max-w-7xl mx-auto space-y-6">
          <div className="flex items-center justify-between">
            <Skeleton className="h-8 w-48" />
            <Skeleton className="h-9 w-24" />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <Skeleton key={i} className="h-32" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto p-6" data-testid="metrics-container">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-foreground">{t('pageTitle')}</h1>
            <p className="text-sm text-muted-foreground">
              {t('lastUpdated', { time: lastUpdated.toLocaleTimeString() })}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Select value={dateRange} onValueChange={(v) => setDateRange(v as DateRange)}>
              <SelectTrigger className="w-32">
                <Calendar size={14} className="mr-2" />
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="1h">{t('dateRange.lastHour')}</SelectItem>
                <SelectItem value="24h">{t('dateRange.last24h')}</SelectItem>
              </SelectContent>
            </Select>
            <Button
              variant={autoRefresh ? "secondary" : "outline"}
              onClick={() => setAutoRefresh(!autoRefresh)}
              className="gap-2"
            >
              <RefreshCw className={cn("w-4 h-4", autoRefresh && "animate-spin [animation-duration:3s]")} />
              {autoRefresh ? t('autoRefresh.on') : t('autoRefresh.off')}
            </Button>
            <Button variant="outline" onClick={handleExportCSV} disabled={filteredRequests.length === 0}>
              <Download className="w-4 h-4 mr-2" />
              {t('exportCSV')}
            </Button>
            <Button variant="outline" onClick={handleRefresh}>
              <RefreshCw className="w-4 h-4 mr-2" />
              {t('refresh')}
            </Button>
          </div>
        </div>

        {/* Error banner */}
        {error && (
          <Card className="border-destructive/50 bg-destructive/10">
            <CardContent className="flex items-center justify-between p-4">
              <div className="flex items-center gap-3">
                <AlertTriangle className="w-5 h-5 text-destructive" />
                <div>
                  <p className="text-sm font-medium text-destructive">{t('error.failedToLoad')}</p>
                  <p className="text-xs text-destructive/80">{error}</p>
                </div>
              </div>
              <Button variant="outline" size="sm" onClick={handleRefresh} className="gap-2">
                <RefreshCw className="w-4 h-4" />
                {t('retry')}
              </Button>
            </CardContent>
          </Card>
        )}

        {/* Animated Latency Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {latencyStats && (
            <>
              <AnimatedMetricCard
                label={t('latencyCards.avgLatency')}
                value={latencyStats.avg_ms}
                icon={Clock}
                color="bg-sky-500"
                gradient="bg-gradient-to-br from-sky-500 to-blue-600"
                delay={0}
              />
              <AnimatedMetricCard
                label={t('latencyCards.p50Latency')}
                value={latencyStats.p50_ms}
                icon={Activity}
                color="bg-violet-500"
                gradient="bg-gradient-to-br from-violet-500 to-purple-600"
                delay={100}
              />
              <AnimatedMetricCard
                label={t('latencyCards.p95Latency')}
                value={latencyStats.p95_ms}
                icon={Zap}
                color="bg-amber-500"
                gradient="bg-gradient-to-br from-amber-500 to-orange-600"
                delay={200}
              />
              <AnimatedMetricCard
                label={t('latencyCards.ttftStreaming')}
                value={latencyStats.ttft_avg_ms || 0}
                icon={Gauge}
                color="bg-emerald-500"
                gradient="bg-gradient-to-br from-emerald-500 to-teal-600"
                delay={300}
              />
            </>
          )}
        </div>

        {/* Tabs */}
        <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as TabType)}>
          <TabsList>
            <TabsTrigger value="overview" className="gap-2">
              <TrendingUp size={14} />
              {t('tabs.overview')}
            </TabsTrigger>
            <TabsTrigger value="queue" className="gap-2">
              <Server size={14} />
              {t('tabs.queue')}
            </TabsTrigger>
          </TabsList>

          {/* Overview Tab */}
          <TabsContent value="overview" className="space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Trend Chart */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <TrendingUp className="w-5 h-5" />
                    {t('charts.latencyTrend')}
                  </CardTitle>
                  <CardDescription>{t('charts.latencyTrendDescription')}</CardDescription>
                </CardHeader>
                <CardContent>
                  {trendData.length === 0 ? (
                    <div className="h-[250px] flex items-center justify-center text-sm text-muted-foreground">
                      {t('charts.noRecentData')}
                    </div>
                  ) : (
                    <ResponsiveContainer width="100%" height={250}>
                      <AreaChart data={trendData}>
                        <defs>
                          <linearGradient id="latencyGradient" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity={0.35} />
                            <stop offset="50%" stopColor="hsl(var(--accent))" stopOpacity={0.15} />
                            <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                        <XAxis dataKey="time" stroke="hsl(var(--muted-foreground))" />
                        <YAxis stroke="hsl(var(--muted-foreground))" />
                        <Tooltip
                          contentStyle={{
                            backgroundColor: "hsl(var(--card))",
                            border: "1px solid hsl(var(--border))",
                            borderRadius: "12px",
                            boxShadow: "var(--shadow-elevated)",
                          }}
                          formatter={(value: number, name: string) => {
                            if (name === "latency") return [`${value} ms`, t('tooltip.avgLatency')];
                            if (name === "requests") return [value, t('tooltip.requests')];
                            return [value, name];
                          }}
                          labelFormatter={(label) => t('tooltip.time', { label })}
                        />
                        {/* Glow line behind */}
                        <Area
                          type="monotone"
                          dataKey="latency"
                          stroke="hsl(var(--primary))"
                          strokeWidth={6}
                          strokeOpacity={0.25}
                          fill="none"
                          dot={false}
                          activeDot={false}
                        />
                        {/* Crisp foreground line */}
                        <Area
                          type="monotone"
                          dataKey="latency"
                          stroke="hsl(var(--primary))"
                          strokeWidth={2.5}
                          fill="url(#latencyGradient)"
                          dot={false}
                          activeDot={{
                            r: 6,
                            strokeWidth: 3,
                            fill: "hsl(var(--primary))",
                            stroke: "hsl(var(--primary-foreground))",
                          }}
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  )}
                  {/* sr-only table for latency trend chart */}
                  {trendData.length > 0 && (
                    <table className="sr-only">
                      <caption>Latency trend data</caption>
                      <thead>
                        <tr><th>Time</th><th>Latency (ms)</th><th>Requests</th></tr>
                      </thead>
                      <tbody>
                        {trendData.map((d, i) => (
                          <tr key={i}><td>{d.time}</td><td>{d.latency}</td><td>{d.requests}</td></tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </CardContent>
              </Card>

              {/* Mode Stats Chart */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Activity className="w-5 h-5" />
                    {t('charts.requestsByMode')}
                  </CardTitle>
                  <CardDescription>{t('charts.requestsByModeDescription')}</CardDescription>
                </CardHeader>
                <CardContent>
                  <div aria-label="Requests by mode bar chart">
                  <ResponsiveContainer width="100%" height={250}>
                    <BarChart data={modeStats}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                      <XAxis dataKey="mode" stroke="hsl(var(--muted-foreground))" />
                      <YAxis stroke="hsl(var(--muted-foreground))" />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "hsl(var(--card))",
                          border: "1px solid hsl(var(--border))",
                          borderRadius: "8px",
                        }}
                        formatter={(value: number) => [value.toLocaleString(), t('tooltip.requests')]}
                        labelFormatter={(label) => t('tooltip.mode', { label })}
                      />
                      <Bar
                        dataKey="request_count"
                        radius={[4, 4, 0, 0]}
                        label={{ position: "top", fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                      >
                        {modeStats.map((_, index) => (
                          <Cell
                            key={`bar-${index}`}
                            fill={MODE_COLORS[index % MODE_COLORS.length]}
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                  </div>
                  {/* sr-only table for bar chart */}
                  <table className="sr-only">
                    <caption>Requests by mode</caption>
                    <thead>
                      <tr><th>Mode</th><th>Request Count</th><th>Avg Latency (ms)</th><th>Success Rate</th></tr>
                    </thead>
                    <tbody>
                      {modeStats.map((m) => (
                        <tr key={m.mode}><td>{m.mode}</td><td>{m.request_count}</td><td>{Math.round(m.avg_latency_ms)}</td><td>{(m.success_rate * 100).toFixed(1)}%</td></tr>
                      ))}
                    </tbody>
                  </table>
                </CardContent>
              </Card>
            </div>

            {/* Performance Charts Row */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {modeStats.length > 0 && (
                <div className="flex flex-col">
                  <RadarMetricCard modeStats={modeStats} />
                  <table className="sr-only">
                    <caption>Performance radar by mode</caption>
                    <thead>
                      <tr><th>Mode</th><th>Avg Latency (ms)</th><th>Requests</th><th>Success Rate</th></tr>
                    </thead>
                    <tbody>
                      {modeStats.map((m) => (
                        <tr key={m.mode}><td>{m.mode}</td><td>{Math.round(m.avg_latency_ms)}</td><td>{m.request_count}</td><td>{(m.success_rate * 100).toFixed(1)}%</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {recentRequests.length > 0 && (
                <div className="flex flex-col">
                  <GlowingDonutCard recentRequests={recentRequests} />
                  <table className="sr-only">
                    <caption>Request distribution data</caption>
                    <thead>
                      <tr><th>Status</th><th>Count</th></tr>
                    </thead>
                    <tbody>
                      <tr><td>Success</td><td>{recentRequests.filter(r => r.status === "success").length}</td></tr>
                      <tr><td>Error</td><td>{recentRequests.filter(r => r.status !== "success").length}</td></tr>
                      <tr><td>Total</td><td>{recentRequests.length}</td></tr>
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {/* Recent Requests Table — Redesigned */}
            <Card>
              {/* Filter Bar */}
              <div className="p-4 pb-0 space-y-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-lg">{t('recentRequests.title')}</CardTitle>
                  <span className="text-xs text-muted-foreground">
                    {t('recentRequests.countSummary', { filtered: filteredRequests.length, total: recentRequests.length })}
                  </span>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  {/* Status chips */}
                  <div className="flex items-center rounded-lg border border-border bg-secondary/30 p-0.5" role="group" aria-label="Filter by status">
                    {(["all", "success", "error"] as const).map(s => (
                      <button
                        key={s}
                        onClick={() => setStatusFilter(s)}
                        aria-pressed={statusFilter === s}
                        className={cn(
                          "px-3 py-1 text-xs font-medium rounded-md transition-all capitalize",
                          statusFilter === s
                            ? "bg-primary text-primary-foreground shadow-sm"
                            : "text-muted-foreground hover:text-foreground"
                        )}
                      >
                        {s === "all" ? t('recentRequests.filterAll') : s === "success" ? <><span aria-hidden="true">&#x2713;</span> {t('recentRequests.filterSuccess')}</> : <><span aria-hidden="true">&#x2715;</span> {t('recentRequests.filterError')}</>}
                      </button>
                    ))}
                  </div>

                  {/* Mode filter */}
                  <Select value={modeFilter} onValueChange={setModeFilter}>
                    <SelectTrigger className="w-[140px] h-8 text-xs">
                      <SelectValue placeholder={t('recentRequests.allModes')} />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">{t('recentRequests.allModes')}</SelectItem>
                      {availableModes.map(m => (
                        <SelectItem key={m} value={m} className="capitalize">{m}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  {/* Search */}
                  <div className="relative flex-1 min-w-[160px] max-w-[280px]">
                    <Activity className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                    <input
                      type="text"
                      placeholder={t('recentRequests.searchPlaceholder')}
                      value={searchQuery}
                      onChange={e => setSearchQuery(e.target.value)}
                      aria-label="Search requests by ID or error"
                      className="w-full h-8 pl-8 pr-3 text-xs rounded-lg border border-border bg-secondary/30 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary/40"
                    />
                  </div>
                </div>

                {/* Summary Strip */}
                <div className="flex flex-wrap gap-4 py-2 px-1 text-xs">
                  <div className="flex items-center gap-1.5">
                    <span className="text-muted-foreground">{t('recentRequests.summary.total')}</span>
                    <span className="font-semibold text-foreground">{requestSummary.total}</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <div className="w-1.5 h-1.5 rounded-full bg-success" />
                    <span className="text-muted-foreground">{t('recentRequests.summary.success')}</span>
                    <span className="font-semibold text-success">{requestSummary.successRate.toFixed(1)}%</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <div className="w-1.5 h-1.5 rounded-full bg-destructive" />
                    <span className="text-muted-foreground">{t('recentRequests.summary.errors')}</span>
                    <span className="font-semibold text-destructive">{requestSummary.errorCount}</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Clock className="w-3 h-3 text-muted-foreground" />
                    <span className="text-muted-foreground">{t('recentRequests.summary.avg')}</span>
                    <span className="font-semibold text-foreground">{formatMs(requestSummary.avgLatency, 1)}</span>
                  </div>
                </div>
              </div>

              <CardContent className="pt-2">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{t('recentRequests.table.time')}</TableHead>
                      <TableHead>{t('recentRequests.table.mode')}</TableHead>
                      <TableHead>{t('recentRequests.table.latency')}</TableHead>
                      <TableHead>{t('recentRequests.table.tokens')}</TableHead>
                      <TableHead>{t('recentRequests.table.status')}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {paginatedRequests.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={5} className="text-center text-muted-foreground py-8">
                          {t('recentRequests.noMatchingRequests')}
                        </TableCell>
                      </TableRow>
                    ) : paginatedRequests.map((request, idx) => (
                      <TableRow
                        key={request.id}
                        className={cn(
                          "cursor-pointer hover:bg-muted/50 transition-colors",
                          idx % 2 === 1 && "bg-muted/20"
                        )}
                        tabIndex={0}
                        onClick={() => setSelectedRequest(request)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            setSelectedRequest(request);
                          }
                        }}
                      >
                        <TableCell className="text-muted-foreground text-xs">
                          {new Date(request.timestamp).toLocaleTimeString()}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline" className="capitalize text-xs">
                            {request.mode}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <span className={cn("text-xs font-mono", getLatencyColor(request.latency_ms))}>
                              {formatMs(request.latency_ms, 1)}
                            </span>
                            <div
                              className="w-16 h-1.5 rounded-full bg-muted overflow-hidden"
                              aria-label={`Latency: ${request.latency_ms < 200 ? "fast" : request.latency_ms < 500 ? "moderate" : "slow"}`}
                              role="img"
                            >
                              <div
                                className={cn(
                                  "h-full rounded-full transition-all",
                                  request.latency_ms < 200 ? "bg-success" :
                                  request.latency_ms < 500 ? "bg-warning" : "bg-destructive"
                                )}
                                style={{ width: `${Math.min((request.latency_ms / maxLatencyInPage) * 100, 100)}%` }}
                              />
                            </div>
                          </div>
                        </TableCell>
                        <TableCell className="text-xs">{request.tokens.toLocaleString()}</TableCell>
                        <TableCell>
                          <div className="flex items-center gap-1.5">
                            <div className={cn(
                              "w-2 h-2 rounded-full",
                              request.status === "success" ? "bg-success" : "bg-destructive"
                            )} />
                            <span className={cn(
                              "text-xs",
                              request.status === "success" ? "text-success" : "text-destructive"
                            )}>
                              {request.status === "success" ? t('recentRequests.statusSuccess') : t('recentRequests.statusError')}
                            </span>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>

                {/* Pagination */}
                {filteredRequests.length > PAGE_SIZE && (
                  <div className="flex items-center justify-between pt-4 border-t border-border mt-2">
                    <span className="text-xs text-muted-foreground">
                      {t('recentRequests.pagination.showing', { start: (safePage - 1) * PAGE_SIZE + 1, end: Math.min(safePage * PAGE_SIZE, filteredRequests.length), total: filteredRequests.length })}
                    </span>
                    <div className="flex items-center gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={safePage <= 1}
                        onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                        className="h-7 text-xs"
                      >
                        {t('recentRequests.pagination.previous')}
                      </Button>
                      <span className="text-xs text-muted-foreground px-2">
                        {safePage} / {totalPages}
                      </span>
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={safePage >= totalPages}
                        onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                        className="h-7 text-xs"
                      >
                        {t('recentRequests.pagination.next')}
                      </Button>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Queue Tab */}
          <TabsContent value="queue" className="space-y-6">
            {!queueStatus ? (
              <Card>
                <CardContent>
                  <EmptyState
                    variant="default"
                    title={t('queue.noData')}
                    description={t('queue.noDataDescription')}
                    action={{
                      label: t('refresh'),
                      onClick: handleRefresh,
                    }}
                    size="md"
                  />
                </CardContent>
              </Card>
            ) : (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <Server className="w-5 h-5" />
                      {t('queue.title')}
                    </CardTitle>
                    <CardDescription>{t('queue.description')}</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-5">
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">{t('queue.status')}</span>
                      <Badge
                        variant="outline"
                        className={cn(
                          queueLevel === "healthy" && "border-success/50 text-success",
                          queueLevel === "busy" && "border-warning/50 text-warning",
                          queueLevel === "overloaded" && "border-destructive/50 text-destructive"
                        )}
                      >
                        {queueLevel ?? "unknown"}
                      </Badge>
                    </div>

                    <div className="space-y-2">
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-muted-foreground">{t('queue.active')}</span>
                        <span className="font-medium">
                          {queueStatus.active} / {queueStatus.max_concurrent}
                        </span>
                      </div>
                      <Progress
                        value={
                          queueStatus.max_concurrent > 0
                            ? (queueStatus.active / queueStatus.max_concurrent) * 100
                            : 0
                        }
                        className="h-2"
                      />
                    </div>

                    <div className="space-y-2">
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-muted-foreground">{t('queue.queued')}</span>
                        <span className="font-medium">
                          {queueStatus.queued} / {queueStatus.max_queue_size}
                        </span>
                      </div>
                      <Progress
                        value={
                          queueStatus.max_queue_size > 0
                            ? (queueStatus.queued / queueStatus.max_queue_size) * 100
                            : 0
                        }
                        className="h-2"
                      />
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle>{t('charts.requestVolume')}</CardTitle>
                    <CardDescription>{t('charts.requestsOverTime')}</CardDescription>
                  </CardHeader>
                  <CardContent>
                    {trendData.length === 0 ? (
                      <div className="h-[250px] flex items-center justify-center text-sm text-muted-foreground">
                        {t('charts.noRecentData')}
                      </div>
                    ) : (
                      <ResponsiveContainer width="100%" height={250}>
                        <BarChart data={trendData}>
                          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                          <XAxis dataKey="time" stroke="hsl(var(--muted-foreground))" />
                          <YAxis stroke="hsl(var(--muted-foreground))" />
                          <Tooltip
                            contentStyle={{
                              backgroundColor: "hsl(var(--card))",
                              border: "1px solid hsl(var(--border))",
                              borderRadius: "8px",
                            }}
                            formatter={(value: number) => [value, t('tooltip.requests')]}
                            labelFormatter={(label) => t('tooltip.time', { label })}
                          />
                          <Bar
                            dataKey="requests"
                            fill="hsl(var(--primary))"
                            radius={[4, 4, 0, 0]}
                            label={{ position: "top", fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                          />
                        </BarChart>
                      </ResponsiveContainer>
                    )}
                    {/* sr-only table for queue request volume chart */}
                    {trendData.length > 0 && (
                      <table className="sr-only">
                        <caption>Request volume over time</caption>
                        <thead>
                          <tr><th>Time</th><th>Requests</th></tr>
                        </thead>
                        <tbody>
                          {trendData.map((d, i) => (
                            <tr key={i}><td>{d.time}</td><td>{d.requests}</td></tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </CardContent>
                </Card>
              </div>
            )}
          </TabsContent>


        </Tabs>

        {/* Request Detail Modal */}
        <Dialog open={!!selectedRequest} onOpenChange={() => setSelectedRequest(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{t('requestDetail.title')}</DialogTitle>
              <DialogDescription>
                {selectedRequest?.id}
              </DialogDescription>
            </DialogHeader>
            {selectedRequest && (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-sm text-muted-foreground">{t('requestDetail.timestamp')}</p>
                    <p className="font-medium">
                      {new Date(selectedRequest.timestamp).toLocaleString()}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">{t('requestDetail.mode')}</p>
                    <p className="font-medium capitalize">{selectedRequest.mode}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">{t('requestDetail.latency')}</p>
                    <p className={cn("font-medium", getLatencyColor(selectedRequest.latency_ms))}>
                      {formatMs(selectedRequest.latency_ms)}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">{t('requestDetail.tokens')}</p>
                    <p className="font-medium">{selectedRequest.tokens.toLocaleString()}</p>
                  </div>
                </div>
                {selectedRequest.error_message && (
                  <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/30">
                    <div className="flex items-center gap-2 text-destructive mb-1">
                      <AlertTriangle className="w-4 h-4" />
                      <span className="font-medium">{t('requestDetail.error')}</span>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      {selectedRequest.error_message}
                    </p>
                  </div>
                )}
              </div>
            )}
          </DialogContent>
        </Dialog>
      </div>
    </div>
  );
};

export default MetricsPage;
