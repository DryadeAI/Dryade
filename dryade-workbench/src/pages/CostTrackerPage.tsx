// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
/**
 * CostTrackerPage - Native workbench page for LLM cost tracking.
 *
 * Converted from plugin iframe to native page (Phase 191).
 * This is a free-core feature available to all users including community.
 * Uses workbench shadcn/ui components directly (no SDK bridge, no iframe).
 *
 * API endpoints: /api/costs, /api/costs/by-model, /api/costs/by-agent,
 * /api/costs/records, /api/costs/realtime, /api/costs/pricing
 */

import { useState, useEffect, useRef, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import EmptyState from "@/components/shared/EmptyState";
import { fetchWithAuth } from "@/services/apiClient";
import {
  DollarSign,
  Activity,
  BarChart3,
  RefreshCw,
  TrendingUp,
  Loader2,
  Plus,
} from "lucide-react";
import { toast } from "sonner";

// ── Types ─────────────────────────────────────────────────────

interface CostSummary {
  total_cost: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_requests: number;
}

interface ModelCost {
  model: string;
  cost: number;
  requests: number;
}

interface AgentCost {
  agent: string;
  cost: number;
  requests: number;
}

interface CostRecord {
  id: string;
  timestamp: string;
  model: string;
  agent_name?: string;
  input_tokens: number;
  output_tokens: number;
  cost: number;
}

interface RealtimeCost {
  total_cost: number;
}

// Backend response types
interface BackendSummary {
  total_cost_usd: number;
  total_input_tokens: number;
  total_output_tokens: number;
  record_count: number;
}

interface BackendBreakdown {
  key: string;
  total_cost: number;
  total_tokens: number;
  request_count: number;
}

interface BackendRecord {
  id: number;
  model: string;
  agent: string | null;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  timestamp: string;
}

interface ModelPricingItem {
  model_name: string;
  provider: string | null;
  input_cost_per_token: number;
  output_cost_per_token: number;
  source: "litellm" | "manual";
  updated_at: string | null;
}

interface PricingListResponse {
  items: ModelPricingItem[];
  total: number;
  has_more: boolean;
}

interface PricingStats {
  total_models: number;
  by_source: Record<string, number>;
}

// ── API helpers ───────────────────────────────────────────────

function getDateRange(period: string) {
  const end = new Date();
  const start = new Date(end);
  switch (period) {
    case "24h": start.setHours(end.getHours() - 24); break;
    case "30d": start.setDate(end.getDate() - 30); break;
    case "90d": start.setDate(end.getDate() - 90); break;
    default: start.setDate(end.getDate() - 7);
  }
  return { start_date: start.toISOString(), end_date: end.toISOString() };
}

async function fetchSummary(range: { start_date: string; end_date: string }): Promise<CostSummary> {
  const qs = new URLSearchParams(range).toString();
  const data = await fetchWithAuth<BackendSummary>(`/costs?${qs}`);
  return {
    total_cost: data.total_cost_usd,
    total_input_tokens: data.total_input_tokens,
    total_output_tokens: data.total_output_tokens,
    total_requests: data.record_count,
  };
}

async function fetchByModel(): Promise<ModelCost[]> {
  const data = await fetchWithAuth<BackendBreakdown[]>("/costs/by-model");
  return data.map((d) => ({ model: d.key, cost: d.total_cost, requests: d.request_count }));
}

async function fetchByAgent(): Promise<AgentCost[]> {
  const data = await fetchWithAuth<BackendBreakdown[]>("/costs/by-agent");
  return data.map((d) => ({ agent: d.key, cost: d.total_cost, requests: d.request_count }));
}

async function fetchRecords(range: { start_date: string; end_date: string }): Promise<CostRecord[]> {
  const qs = new URLSearchParams({ limit: "20", ...range }).toString();
  const data = await fetchWithAuth<{ items: BackendRecord[] }>(`/costs/records?${qs}`);
  return data.items.map((r) => ({
    id: String(r.id),
    timestamp: r.timestamp,
    model: r.model,
    agent_name: r.agent || undefined,
    input_tokens: r.input_tokens,
    output_tokens: r.output_tokens,
    cost: r.cost_usd,
  }));
}

async function fetchRealtime(): Promise<RealtimeCost> {
  const data = await fetchWithAuth<BackendSummary>("/costs/realtime");
  return { total_cost: data.total_cost_usd };
}

// ── Formatting ────────────────────────────────────────────────

const formatCurrency = (val: number) => `$${val.toFixed(2)}`;
const formatTokens = (val: number) => {
  if (val >= 1_000_000) return `${(val / 1_000_000).toFixed(1)}M`;
  if (val >= 1_000) return `${(val / 1_000).toFixed(1)}K`;
  return String(val);
};
const formatCostPer1M = (perToken: number) => {
  const per1M = perToken * 1_000_000;
  return per1M < 0.01 ? `$${per1M.toFixed(4)}` : `$${per1M.toFixed(2)}`;
};

// ── Period options ────────────────────────────────────────────

const PERIOD_OPTIONS = [
  { value: "24h", label: "Last 24 hours" },
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
  { value: "90d", label: "Last 90 days" },
];

// ── Stats Card ────────────────────────────────────────────────

function StatsCard({
  title,
  value,
  icon,
  loading,
}: {
  title: string;
  value: string;
  icon: React.ReactNode;
  loading: boolean;
}) {
  return (
    <Card className="bg-card/60 backdrop-blur-md">
      <CardContent className="p-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs text-muted-foreground">{title}</p>
            {loading ? (
              <Skeleton className="h-7 w-20 mt-1" />
            ) : (
              <p className="text-2xl font-bold">{value}</p>
            )}
          </div>
          <div className="p-2 rounded-lg bg-primary/10 text-primary">{icon}</div>
        </div>
      </CardContent>
    </Card>
  );
}

// ── Pricing Tab ───────────────────────────────────────────────

function PricingTabContent() {
  const [pricing, setPricing] = useState<ModelPricingItem[]>([]);
  const [stats, setStats] = useState<PricingStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [search, setSearch] = useState("");
  const [editingModel, setEditingModel] = useState<string | null>(null);
  const [editInput, setEditInput] = useState("");
  const [editOutput, setEditOutput] = useState("");
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [addingModel, setAddingModel] = useState(false);
  const [newModelName, setNewModelName] = useState("");
  const [newInputCost, setNewInputCost] = useState("");
  const [newOutputCost, setNewOutputCost] = useState("");
  const PAGE_SIZE = 50;

  const fetchPricing = useCallback(async (searchVal?: string) => {
    setLoading(true);
    setError(null);
    try {
      const qs = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(page * PAGE_SIZE) });
      if (searchVal) qs.set("search", searchVal);
      const [pricingRes, statsRes] = await Promise.all([
        fetchWithAuth<PricingListResponse>(`/costs/pricing?${qs}`),
        fetchWithAuth<PricingStats>("/costs/pricing/stats"),
      ]);
      setPricing(pricingRes.items);
      setTotal(pricingRes.total);
      setStats(statsRes);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load pricing data");
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    void fetchPricing(search);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page]);

  const handleSearch = () => {
    setPage(0);
    void fetchPricing(search);
  };

  const handleSync = async () => {
    setSyncing(true);
    setSyncMessage(null);
    try {
      const result = await fetchWithAuth<{ synced: number; skipped_manual: number; total: number }>(
        "/costs/pricing/sync",
        { method: "POST" },
      );
      setSyncMessage(`Synced ${result.synced} models (${result.skipped_manual} manual preserved, ${result.total} total)`);
      await fetchPricing(search);
    } catch (err) {
      if (err instanceof Error && err.message.includes("503")) {
        setSyncMessage("LiteLLM is not installed. Install it to auto-populate pricing.");
      } else {
        setSyncMessage("Failed to sync pricing from LiteLLM.");
      }
    } finally {
      setSyncing(false);
    }
  };

  const handleSave = async (modelName: string) => {
    try {
      const inputCost = parseFloat(editInput) / 1_000_000;
      const outputCost = parseFloat(editOutput) / 1_000_000;
      await fetchWithAuth(`/costs/pricing/${encodeURIComponent(modelName)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ input_cost_per_token: inputCost, output_cost_per_token: outputCost }),
      });
      setEditingModel(null);
      await fetchPricing(search);
    } catch {
      toast.error("Failed to update pricing");
    }
  };

  const handleAddModel = async () => {
    if (!newModelName.trim() || !newInputCost || !newOutputCost) return;
    try {
      const inputCost = parseFloat(newInputCost) / 1_000_000;
      const outputCost = parseFloat(newOutputCost) / 1_000_000;
      await fetchWithAuth(`/costs/pricing/${encodeURIComponent(newModelName.trim())}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ input_cost_per_token: inputCost, output_cost_per_token: outputCost }),
      });
      setAddingModel(false);
      setNewModelName("");
      setNewInputCost("");
      setNewOutputCost("");
      await fetchPricing(search);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add model pricing");
    }
  };

  const startEdit = (item: ModelPricingItem) => {
    setEditingModel(item.model_name);
    setEditInput(String((item.input_cost_per_token * 1_000_000).toFixed(2)));
    setEditOutput(String((item.output_cost_per_token * 1_000_000).toFixed(2)));
  };

  if (loading && pricing.length === 0) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {stats && (
        <div className="flex gap-4 text-sm text-muted-foreground">
          <span>{stats.total_models} models</span>
          {stats.by_source.litellm && <span>{stats.by_source.litellm} from LiteLLM</span>}
          {stats.by_source.manual && <span>{stats.by_source.manual} manual</span>}
        </div>
      )}

      <div className="flex gap-2 items-center">
        <Input
          placeholder="Search models..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          className="flex-1 max-w-sm"
        />
        <Button variant="outline" onClick={handleSearch}>Search</Button>
        <Button variant="outline" onClick={() => void handleSync()} disabled={syncing}>
          {syncing ? <Loader2 className="w-4 h-4 mr-1 motion-safe:animate-spin" /> : <RefreshCw className="w-4 h-4 mr-1" />}
          Refresh from LiteLLM
        </Button>
        <Button onClick={() => setAddingModel(true)}>
          <Plus className="w-4 h-4 mr-1" />
          Add Model
        </Button>
      </div>

      {error && (
        <div className="text-sm p-2 rounded bg-destructive/10 text-destructive">{error}</div>
      )}

      {syncMessage && (
        <div className="text-sm p-2 rounded bg-muted">{syncMessage}</div>
      )}

      {addingModel && (
        <Card>
          <CardContent className="p-4">
            <h3 className="text-base font-semibold mb-3">Add Model Pricing</h3>
            <div className="flex gap-2 items-end">
              <div className="flex-1">
                <label className="text-xs text-muted-foreground mb-1 block">Model Name</label>
                <Input
                  placeholder="e.g. claude-sonnet-4"
                  value={newModelName}
                  onChange={(e) => setNewModelName(e.target.value)}
                />
              </div>
              <div className="w-32">
                <label className="text-xs text-muted-foreground mb-1 block">Input $/1M tokens</label>
                <Input
                  placeholder="3.00"
                  value={newInputCost}
                  onChange={(e) => setNewInputCost(e.target.value)}
                />
              </div>
              <div className="w-32">
                <label className="text-xs text-muted-foreground mb-1 block">Output $/1M tokens</label>
                <Input
                  placeholder="15.00"
                  value={newOutputCost}
                  onChange={(e) => setNewOutputCost(e.target.value)}
                />
              </div>
              <Button onClick={() => void handleAddModel()}>Save</Button>
              <Button variant="ghost" onClick={() => setAddingModel(false)}>Cancel</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {!loading && pricing.length === 0 ? (
        <EmptyState
          icon={<DollarSign className="w-8 h-8 text-muted-foreground" />}
          title="No pricing data"
          description="Click 'Refresh from LiteLLM' to populate model pricing, or add models manually."
        />
      ) : (
        <>
          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Model</TableHead>
                    <TableHead>Provider</TableHead>
                    <TableHead className="text-right">Input $/1M</TableHead>
                    <TableHead className="text-right">Output $/1M</TableHead>
                    <TableHead>Source</TableHead>
                    <TableHead>Updated</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {pricing.map((item) => (
                    <TableRow key={item.model_name}>
                      <TableCell className="font-mono text-sm">{item.model_name}</TableCell>
                      <TableCell className="text-muted-foreground">{item.provider || "-"}</TableCell>
                      {editingModel === item.model_name ? (
                        <>
                          <TableCell className="text-right">
                            <Input
                              value={editInput}
                              onChange={(e) => setEditInput(e.target.value)}
                              className="w-24 text-right"
                            />
                          </TableCell>
                          <TableCell className="text-right">
                            <Input
                              value={editOutput}
                              onChange={(e) => setEditOutput(e.target.value)}
                              className="w-24 text-right"
                            />
                          </TableCell>
                        </>
                      ) : (
                        <>
                          <TableCell className="text-right font-mono">{formatCostPer1M(item.input_cost_per_token)}</TableCell>
                          <TableCell className="text-right font-mono">{formatCostPer1M(item.output_cost_per_token)}</TableCell>
                        </>
                      )}
                      <TableCell>
                        <Badge variant={item.source === "manual" ? "outline" : "secondary"}>
                          {item.source}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {item.updated_at ? new Date(item.updated_at).toLocaleDateString() : "-"}
                      </TableCell>
                      <TableCell>
                        {editingModel === item.model_name ? (
                          <div className="flex gap-1">
                            <Button size="sm" onClick={() => void handleSave(item.model_name)}>Save</Button>
                            <Button variant="ghost" size="sm" onClick={() => setEditingModel(null)}>Cancel</Button>
                          </div>
                        ) : (
                          <Button variant="ghost" size="sm" onClick={() => startEdit(item)}>Edit</Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          {total > PAGE_SIZE && (
            <div className="flex justify-between items-center text-sm">
              <span className="text-muted-foreground">
                Showing {page * PAGE_SIZE + 1}-{Math.min((page + 1) * PAGE_SIZE, total)} of {total}
              </span>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
                  Previous
                </Button>
                <Button variant="outline" size="sm" disabled={(page + 1) * PAGE_SIZE >= total} onClick={() => setPage((p) => p + 1)}>
                  Next
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ── Main Page Component ───────────────────────────────────────

type CostTab = "overview" | "by-model" | "by-agent" | "records" | "pricing";

const CostTrackerPage = () => {
  const { t } = useTranslation();
  const [tab, setTab] = useState<CostTab>("overview");
  const [period, setPeriod] = useState("7d");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<CostSummary | null>(null);
  const [modelCosts, setModelCosts] = useState<ModelCost[]>([]);
  const [agentCosts, setAgentCosts] = useState<AgentCost[]>([]);
  const [records, setRecords] = useState<CostRecord[]>([]);
  const [realtimeCost, setRealtimeCost] = useState(0);
  const [deltaFromLoad, setDeltaFromLoad] = useState(0);
  const baselineRef = useRef<number | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const range = getDateRange(period);
      const results = await Promise.allSettled([
        fetchSummary(range),
        fetchByModel(),
        fetchByAgent(),
        fetchRecords(range),
      ]);

      if (results[0].status === "fulfilled") setSummary(results[0].value);
      if (results[1].status === "fulfilled") setModelCosts(results[1].value);
      if (results[2].status === "fulfilled") setAgentCosts(results[2].value);
      if (results[3].status === "fulfilled") setRecords(results[3].value);

      const allFailed = results.every((r) => r.status === "rejected");
      if (allFailed) {
        const firstError = results[0].status === "rejected" ? results[0].reason : null;
        setError(firstError instanceof Error ? firstError.message : "Failed to load data");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  }, [period]);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  // Realtime polling
  useEffect(() => {
    let active = true;
    baselineRef.current = null;

    const poll = async () => {
      try {
        const data = await fetchRealtime();
        if (!active) return;
        setRealtimeCost(data.total_cost);
        if (baselineRef.current === null) {
          baselineRef.current = data.total_cost;
        }
        setDeltaFromLoad(Math.max(0, data.total_cost - (baselineRef.current || 0)));
      } catch {
        // Ignore polling errors
      }
    };

    void poll();
    const interval = setInterval(() => void poll(), 5000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  const maxModelCost = Math.max(...modelCosts.map((m) => m.cost), 1);
  const maxAgentCost = Math.max(...agentCosts.map((a) => a.cost), 1);

  return (
    <div className="p-6 space-y-6 h-full overflow-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-foreground flex items-center gap-2">
            <DollarSign className="w-6 h-6" aria-hidden="true" />
            {t("costTracker.title", "Cost Tracking")}
          </h1>
          <p className="text-muted-foreground">{t("costTracker.subtitle", "Monitor LLM usage and spending")}</p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            className="h-9 rounded-md border border-input bg-background px-3 text-sm"
          >
            {PERIOD_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
          <Button variant="outline" onClick={() => void fetchData()} disabled={loading}>
            {loading ? (
              <Loader2 className="w-4 h-4 mr-1 motion-safe:animate-spin" aria-hidden="true" />
            ) : (
              <RefreshCw className="w-4 h-4 mr-1" aria-hidden="true" />
            )}
            Refresh
          </Button>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-lg bg-destructive/10 text-destructive text-sm">{error}</div>
      )}

      {/* Stats Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatsCard
          title="Total Cost"
          value={formatCurrency(summary?.total_cost || 0)}
          icon={<DollarSign size={20} />}
          loading={loading}
        />
        <StatsCard
          title="Total Tokens"
          value={formatTokens((summary?.total_input_tokens || 0) + (summary?.total_output_tokens || 0))}
          icon={<Activity size={20} />}
          loading={loading}
        />
        <StatsCard
          title="Requests"
          value={(summary?.total_requests || 0).toLocaleString()}
          icon={<BarChart3 size={20} />}
          loading={loading}
        />
        <StatsCard
          title="Avg per Request"
          value={formatCurrency(summary && summary.total_requests > 0 ? summary.total_cost / summary.total_requests : 0)}
          icon={<TrendingUp size={20} />}
          loading={loading}
        />
      </div>

      {/* Live Ticker */}
      <Card className="bg-card/60 backdrop-blur-md border-primary/20">
        <CardContent className="p-4 flex items-center gap-3">
          <span className="relative flex h-3 w-3">
            <span className="motion-safe:animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75" />
            <span className="relative inline-flex rounded-full h-3 w-3 bg-primary" />
          </span>
          <span className="text-lg font-semibold">{formatCurrency(realtimeCost)}</span>
          <span className="text-muted-foreground text-sm">(+{formatCurrency(deltaFromLoad)} since page load)</span>
          <Badge className="bg-primary/10 text-primary border-primary/30">Live</Badge>
        </CardContent>
      </Card>

      {/* Tabs */}
      <Tabs value={tab} onValueChange={(v) => setTab(v as CostTab)} className="space-y-4">
        <TabsList className="bg-muted/50">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="by-model">By Model</TabsTrigger>
          <TabsTrigger value="by-agent">By Agent</TabsTrigger>
          <TabsTrigger value="records">Records</TabsTrigger>
          <TabsTrigger value="pricing">Pricing</TabsTrigger>
        </TabsList>

        {/* Overview */}
        <TabsContent value="overview">
          {!loading && summary?.total_requests === 0 ? (
            <EmptyState
              icon={<DollarSign className="w-8 h-8 text-muted-foreground" />}
              title="No cost data yet"
              description="Cost records will appear here once LLM requests are made. Check the Pricing tab to configure model pricing."
            />
          ) : loading ? (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {Array.from({ length: 2 }).map((_, i) => (
                <Card key={i}><CardContent className="p-4"><Skeleton className="h-48 w-full" /></CardContent></Card>
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">Cost by Model</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {modelCosts.slice(0, 6).map((m) => (
                    <div key={m.model} className="flex items-center gap-3">
                      <div className="w-28 text-sm font-medium truncate" title={m.model}>{m.model}</div>
                      <div className="flex-1 h-6 bg-muted rounded overflow-hidden">
                        <div
                          className="h-full bg-primary rounded motion-safe:transition-all motion-safe:duration-300"
                          style={{ width: `${(m.cost / maxModelCost) * 100}%` }}
                        />
                      </div>
                      <div className="w-20 text-right text-sm font-mono">{formatCurrency(m.cost)}</div>
                    </div>
                  ))}
                  {modelCosts.length === 0 && (
                    <p className="text-sm text-muted-foreground text-center py-4">No model data</p>
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">Cost by Agent</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {agentCosts.slice(0, 6).map((a) => (
                    <div key={a.agent} className="flex items-center gap-3">
                      <div className="w-28 text-sm font-medium truncate" title={a.agent}>{a.agent || "Unknown"}</div>
                      <div className="flex-1 h-6 bg-muted rounded overflow-hidden">
                        <div
                          className="h-full bg-accent-secondary rounded motion-safe:transition-all motion-safe:duration-300"
                          style={{ width: `${(a.cost / maxAgentCost) * 100}%` }}
                        />
                      </div>
                      <div className="w-20 text-right text-sm font-mono">{formatCurrency(a.cost)}</div>
                    </div>
                  ))}
                  {agentCosts.length === 0 && (
                    <p className="text-sm text-muted-foreground text-center py-4">No agent data</p>
                  )}
                </CardContent>
              </Card>
            </div>
          )}
        </TabsContent>

        {/* By Model */}
        <TabsContent value="by-model">
          {loading ? (
            <Skeleton className="h-48 w-full" />
          ) : modelCosts.length === 0 ? (
            <EmptyState icon={<BarChart3 className="w-8 h-8 text-muted-foreground" />} title="No model data" description="Model cost breakdowns will appear once requests are made." />
          ) : (
            <Card>
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Model</TableHead>
                      <TableHead className="text-right">Total Cost</TableHead>
                      <TableHead className="text-right">Requests</TableHead>
                      <TableHead className="text-right">Avg/Request</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {modelCosts.map((m) => (
                      <TableRow key={m.model}>
                        <TableCell>{m.model}</TableCell>
                        <TableCell className="text-right font-mono">{formatCurrency(m.cost)}</TableCell>
                        <TableCell className="text-right font-mono">{m.requests}</TableCell>
                        <TableCell className="text-right font-mono">{formatCurrency(m.requests > 0 ? m.cost / m.requests : 0)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* By Agent */}
        <TabsContent value="by-agent">
          {loading ? (
            <Skeleton className="h-48 w-full" />
          ) : agentCosts.length === 0 ? (
            <EmptyState icon={<BarChart3 className="w-8 h-8 text-muted-foreground" />} title="No agent data" description="Agent cost breakdowns will appear once requests are made." />
          ) : (
            <Card>
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Agent</TableHead>
                      <TableHead className="text-right">Total Cost</TableHead>
                      <TableHead className="text-right">Requests</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {agentCosts.map((a) => (
                      <TableRow key={a.agent}>
                        <TableCell>{a.agent || "Unknown"}</TableCell>
                        <TableCell className="text-right font-mono">{formatCurrency(a.cost)}</TableCell>
                        <TableCell className="text-right font-mono">{a.requests}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Records */}
        <TabsContent value="records">
          {loading ? (
            <Skeleton className="h-48 w-full" />
          ) : records.length === 0 ? (
            <EmptyState icon={<Activity className="w-8 h-8 text-muted-foreground" />} title="No records" description="Usage records will appear once LLM requests are made." />
          ) : (
            <Card>
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Timestamp</TableHead>
                      <TableHead>Model</TableHead>
                      <TableHead>Agent</TableHead>
                      <TableHead className="text-right">Input</TableHead>
                      <TableHead className="text-right">Output</TableHead>
                      <TableHead className="text-right">Cost</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {records.slice(0, 15).map((r) => (
                      <TableRow key={r.id}>
                        <TableCell className="text-xs text-muted-foreground">
                          {new Date(r.timestamp).toLocaleString()}
                        </TableCell>
                        <TableCell>{r.model}</TableCell>
                        <TableCell>{r.agent_name || "-"}</TableCell>
                        <TableCell className="text-right font-mono">{r.input_tokens}</TableCell>
                        <TableCell className="text-right font-mono">{r.output_tokens}</TableCell>
                        <TableCell className="text-right font-mono">{formatCurrency(r.cost)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Pricing */}
        <TabsContent value="pricing">
          <PricingTabContent />
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default CostTrackerPage;
