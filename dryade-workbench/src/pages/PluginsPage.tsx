// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useCallback, useEffect, useState } from "react";
import {
  Puzzle, Search,
  RefreshCw, Settings, CheckCircle2,
  AlertCircle, XCircle, Store, ChevronDown,
  Download, Lock, Loader2, PackageOpen,
  Sparkles, ArrowUpRight,
} from "lucide-react";
import { resolvePluginIcon } from "@/lib/plugin-icons";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { pluginsApi, marketplaceApi } from "@/services/api";
import { fetchWithAuth } from "@/services/apiClient";
import type { Plugin, MarketplacePlugin } from "@/types/extended-api";
import { PluginImportDropzone } from "@/components/plugins/PluginImportDropzone";
import { InstalledPluginCard, type InstalledPlugin } from "@/components/plugins/InstalledPluginCard";
import { CheckForUpdatesButton } from "@/components/plugins/CheckForUpdatesButton";
import { PluginSettingsForm } from "@/components/plugins/PluginSettingsForm";
import { IconChooser } from "@/components/plugins/IconChooser";
import { usePluginConfigWithSchema, useUpdatePluginConfig } from "@/hooks/useApi";
import { useTranslation } from "react-i18next";

async function fetchInstalledPlugins(): Promise<InstalledPlugin[]> {
  return fetchWithAuth<InstalledPlugin[]>("/plugins/installed");
}

// Free-core features excluded from plugin list (Phase 191)
// These render as native workbench pages, not plugin iframes
const FREE_CORE_PLUGINS = new Set(["clarify", "cost_tracker"]);

// ---------------------------------------------------------------------------
// Marketplace Teaser - shown in community mode (no PM, no plugins loaded)
// ---------------------------------------------------------------------------
interface TeaserPlugin {
  name: string;
  display_name: string;
  description: string;
  tier: "starter" | "team" | "enterprise";
}

const TEASER_PLUGINS: TeaserPlugin[] = [
  { name: "audio", display_name: "Audio Transcription", description: "Meeting transcription with AI-powered summaries, speaker detection, and searchable archives.", tier: "starter" },
  { name: "templates", display_name: "Templates", description: "Organizational templates with versioning, categories, approval workflows, and usage analytics.", tier: "starter" },
  { name: "skill_editor", display_name: "Skill Editor", description: "Visual YAML editor for agent skills with multi-format import, preview, and testing tools.", tier: "team" },
  { name: "knowledge_advanced", display_name: "Advanced Knowledge", description: "Semantic chunking, custom embeddings, multi-modal RAG, and re-ranking for knowledge bases.", tier: "team" },
  { name: "sandbox", display_name: "Code Sandbox", description: "Configurable code execution isolation with PROCESS, CONTAINER, and gVisor levels.", tier: "team" },
  { name: "compliance_auditor", display_name: "Compliance Auditor", description: "Automated compliance auditing with report generation and remediation tracking.", tier: "enterprise" },
  { name: "enterprise_search", display_name: "Enterprise Search", description: "Cross-MCP server search with federated queries and result aggregation.", tier: "enterprise" },
  { name: "trainer", display_name: "AI Trainer", description: "Training content generation, assessment creation, and learning path management.", tier: "enterprise" },
];

const MarketplaceTeaser = ({ t }: { t: (key: string, options?: Record<string, unknown>) => string }) => (
  <div className="space-y-6">
    <div className="text-center py-6">
      <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-primary/10 mb-4">
        <Sparkles className="w-8 h-8 text-primary" aria-hidden="true" />
      </div>
      <h2 className="text-xl font-semibold mb-2">Extend Dryade with Plugins</h2>
      <p className="text-muted-foreground max-w-lg mx-auto">
        Unlock industry-specific tools, advanced AI capabilities, and enterprise features.
        Your data is preserved if you upgrade or downgrade at any time.
      </p>
    </div>

    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
      {TEASER_PLUGINS.map((plugin) => (
        <Card key={plugin.name} className="flex flex-col justify-between bg-card/60 backdrop-blur-md border-border/50 hover:border-primary/30 transition-colors">
          <CardHeader className="pb-2">
            <div className="flex items-start justify-between gap-2">
              <CardTitle className="text-base leading-tight">{plugin.display_name}</CardTitle>
              <Badge variant="outline" className={getTierBadgeClass(plugin.tier)}>
                {plugin.tier}
              </Badge>
            </div>
            <CardDescription className="line-clamp-3 text-xs mt-1">
              {plugin.description}
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-0">
            <Badge
              variant="outline"
              className="w-full justify-center py-1.5 bg-muted/50 text-muted-foreground border-border/50 cursor-default"
            >
              <Lock className="w-3.5 h-3.5 mr-1.5" aria-hidden="true" />
              {t('marketplace.requires', { tier: plugin.tier })}
            </Badge>
          </CardContent>
        </Card>
      ))}
    </div>

    <div className="text-center">
      <a
        href="https://dryade.ai/pricing"
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-2 px-6 py-3 rounded-lg bg-primary text-primary-foreground font-medium hover:bg-primary/90 transition-colors"
      >
        <Sparkles className="w-4 h-4" aria-hidden="true" />
        View Plans & Pricing
        <ArrowUpRight className="w-4 h-4" aria-hidden="true" />
      </a>
    </div>
  </div>
);


// ---------------------------------------------------------------------------
// Tier badge colours
// ---------------------------------------------------------------------------
const getTierBadgeClass = (tier: string): string => {
  switch (tier) {
    case "starter":
      return "bg-green-500/10 text-green-600 border-green-500/30";
    case "team":
      return "bg-blue-500/10 text-blue-600 border-blue-500/30";
    case "enterprise":
      return "bg-purple-500/10 text-purple-600 border-purple-500/30";
    default:
      return "bg-muted/10 text-muted-foreground border-border/30";
  }
};

const getCategoryBadgeClass = (_category: string): string =>
  "bg-muted/10 text-muted-foreground border-border/50";

// ---------------------------------------------------------------------------
// Marketplace card
// ---------------------------------------------------------------------------
const MarketplaceCard = ({
  plugin,
  installingName,
  onInstall,
  t,
}: {
  plugin: MarketplacePlugin;
  installingName: string | null;
  onInstall: (name: string) => void;
  t: (key: string, options?: Record<string, unknown>) => string;
}) => {
  const isInstalling = installingName === plugin.name;

  return (
    <Card className="flex flex-col justify-between bg-card/60 backdrop-blur-md hover:border-primary/50 transition-colors">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-base leading-tight">
            {plugin.display_name}
          </CardTitle>
          <Badge variant="outline" className={getTierBadgeClass(plugin.tier)}>
            {plugin.tier}
          </Badge>
        </div>
        <CardDescription className="line-clamp-2 text-xs mt-1">
          {plugin.description}
        </CardDescription>
      </CardHeader>

      <CardContent className="pt-0 space-y-3">
        {/* Meta row */}
        <div className="flex items-center gap-2 flex-wrap text-xs text-muted-foreground">
          <Badge variant="outline" className={getCategoryBadgeClass(plugin.category)}>
            {plugin.category.replace("_", " ")}
          </Badge>
          <span>v{plugin.version}</span>
          {plugin.author && <span>{t('marketplace.byAuthor', { author: plugin.author })}</span>}
        </div>

        {/* Action button */}
        {plugin.installed ? (
          <Badge className="w-full justify-center py-1.5 bg-muted text-muted-foreground hover:bg-muted">
            <CheckCircle2 className="w-3.5 h-3.5 mr-1.5" aria-hidden="true" />
            {t('marketplace.installed')}
          </Badge>
        ) : plugin.available ? (
          <Button
            size="sm"
            className="w-full"
            disabled={isInstalling}
            onClick={() => onInstall(plugin.name)}
          >
            {isInstalling ? (
              <>
                <Loader2 className="w-3.5 h-3.5 mr-1.5 motion-safe:animate-spin" aria-hidden="true" />
                {t('actions.installing')}
              </>
            ) : (
              <>
                <Download className="w-3.5 h-3.5 mr-1.5" aria-hidden="true" />
                {t('actions.install')}
              </>
            )}
          </Button>
        ) : (
          <Badge
            variant="outline"
            className="w-full justify-center py-1.5 bg-orange-500/10 text-orange-600 border-orange-500/30 cursor-default"
          >
            <Lock className="w-3.5 h-3.5 mr-1.5" aria-hidden="true" />
            {t('marketplace.requires', { tier: plugin.tier })}
          </Badge>
        )}
      </CardContent>
    </Card>
  );
};

// ---------------------------------------------------------------------------
// Skeleton card for loading state
// ---------------------------------------------------------------------------
const SkeletonCard = () => (
  <Card className="bg-card/60 backdrop-blur-md motion-safe:animate-pulse">
    <CardHeader className="pb-2 space-y-2">
      <div className="h-4 w-3/4 bg-muted rounded" />
      <div className="h-3 w-full bg-muted/60 rounded" />
      <div className="h-3 w-2/3 bg-muted/60 rounded" />
    </CardHeader>
    <CardContent className="pt-0 space-y-3">
      <div className="flex gap-2">
        <div className="h-5 w-16 bg-muted/50 rounded" />
        <div className="h-5 w-12 bg-muted/50 rounded" />
      </div>
      <div className="h-8 w-full bg-muted/40 rounded" />
    </CardContent>
  </Card>
);

// ---------------------------------------------------------------------------
// Main page component
// ---------------------------------------------------------------------------
const PluginsPage = () => {
  const { t } = useTranslation('plugins');
  const [plugins, setPlugins] = useState<Plugin[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [togglingPlugin, setTogglingPlugin] = useState<string | null>(null);
  const [pluginSearch, setPluginSearch] = useState("");
  const [expandedPlugin, setExpandedPlugin] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState("plugins");

  // Installed plugins (on-disk, may differ from loaded)
  const {
    data: installedPlugins,
    isLoading: installedLoading,
    refetch: refetchInstalled,
  } = useQuery<InstalledPlugin[]>({
    queryKey: ["plugins", "installed"],
    queryFn: fetchInstalledPlugins,
    staleTime: 30_000,
  });

  // Marketplace state
  const [marketplacePlugins, setMarketplacePlugins] = useState<MarketplacePlugin[]>([]);
  const [marketplaceLoading, setMarketplaceLoading] = useState(false);
  const [marketplaceSearch, setMarketplaceSearch] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string>("all");
  const [categories, setCategories] = useState<string[]>([]);
  const [installingPlugin, setInstallingPlugin] = useState<string | null>(null);

  // ------- Installed plugins -------
  const loadPlugins = async () => {
    setIsLoading(true);
    try {
      const { plugins: loaded } = await pluginsApi.getPlugins();
      setPlugins(loaded);
    } catch (error) {
      console.error("Failed to load plugins:", error);
      toast.error(t('toast.loadFailed'));
    } finally {
      setIsLoading(false);
    }
    // Also refresh installed list
    void refetchInstalled();
  };

  useEffect(() => {
    void loadPlugins();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const togglePlugin = async (name: string, enabled: boolean) => {
    setTogglingPlugin(name);
    try {
      const updated = await pluginsApi.togglePlugin(name, enabled);
      setPlugins((prev) => prev.map((p) => (p.name === name ? updated : p)));
      toast.success(t('toast.statusUpdated'));
    } catch (error) {
      console.error("Failed to toggle plugin:", error);
      toast.error(t('toast.statusUpdateFailed'));
    } finally {
      setTogglingPlugin(null);
    }
  };

  // ------- Marketplace -------
  const loadMarketplace = useCallback(async () => {
    setMarketplaceLoading(true);
    try {
      const [catalogRes, categoriesRes] = await Promise.all([
        marketplaceApi.getCatalog(),
        marketplaceApi.getCategories(),
      ]);
      setMarketplacePlugins(catalogRes.plugins);
      setCategories(categoriesRes.categories);
    } catch (error) {
      console.error("Failed to load marketplace:", error);
      toast.error(t('toast.marketplaceLoadFailed'));
    } finally {
      setMarketplaceLoading(false);
    }
  }, [t]);

  useEffect(() => {
    if (activeTab === "marketplace" && marketplacePlugins.length === 0) {
      void loadMarketplace();
    }
  }, [activeTab, marketplacePlugins.length, loadMarketplace]);

  const handleInstall = async (pluginName: string) => {
    setInstallingPlugin(pluginName);
    try {
      const result = await marketplaceApi.installPlugin(pluginName);
      if (result.success) {
        toast.success(result.message);
        // Refresh both lists
        setMarketplacePlugins((prev) =>
          prev.map((p) => (p.name === pluginName ? { ...p, installed: true } : p))
        );
        void loadPlugins();
      } else {
        toast.error(result.message);
      }
    } catch (error) {
      console.error("Install failed:", error);
      const msg = error instanceof Error ? error.message : t('toast.installFailed');
      toast.error(msg);
    } finally {
      setInstallingPlugin(null);
    }
  };

  // ------- Helpers -------
  const getPluginStatusIndicator = (status: Plugin["status"]) => {
    switch (status) {
      case "enabled": return <span className="flex items-center gap-1 text-success text-xs font-medium"><CheckCircle2 className="w-4 h-4" aria-hidden="true" /> {t('status.active')}</span>;
      case "disabled": return <span className="flex items-center gap-1 text-muted-foreground text-xs font-medium"><XCircle className="w-4 h-4" aria-hidden="true" /> {t('status.inactive')}</span>;
      case "error": return <span className="flex items-center gap-1 text-destructive text-xs font-medium"><AlertCircle className="w-4 h-4" aria-hidden="true" /> {t('status.error')}</span>;
      default: return null;
    }
  };

  const getCategoryColor = (category: Plugin["category"]) => {
    switch (category) {
      case "pipeline": return "bg-info/10 text-info border-info/30";
      case "backend": return "bg-accent-secondary/10 text-accent-secondary border-accent-secondary/30";
      case "utility": return "bg-warning/10 text-warning border-warning/30";
    }
  };

  const getHealthColor = (health: Plugin["health"]) => {
    switch (health) {
      case "healthy": return "border-success/50 text-success";
      case "degraded": return "border-warning/50 text-warning";
      case "unhealthy": return "border-destructive/50 text-destructive";
    }
  };

  // Filter out free-core plugins (they render as native pages, not plugin UI)
  const filteredPlugins = plugins
    .filter(p => !FREE_CORE_PLUGINS.has(p.name))
    .filter(p => p.display_name.toLowerCase().includes(pluginSearch.toLowerCase()));

  // Community mode: no PM running, no plugins loaded
  const isCommunityMode = !isLoading && plugins.length === 0;

  // Filter marketplace plugins client-side
  const filteredMarketplace = marketplacePlugins.filter((p) => {
    if (selectedCategory !== "all" && p.category !== selectedCategory) return false;
    if (marketplaceSearch) {
      const q = marketplaceSearch.toLowerCase();
      return (
        p.name.toLowerCase().includes(q) ||
        p.display_name.toLowerCase().includes(q) ||
        p.description.toLowerCase().includes(q)
      );
    }
    return true;
  });

  // Plugin Item with inline expandable config + schema-driven settings form
  const PluginListItem = ({ plugin }: { plugin: Plugin }) => {
    const isExpanded = expandedPlugin === plugin.name;
    const PluginIcon = resolvePluginIcon(plugin.icon);

    // Only fetch config+schema when expanded
    const { data: configData, isLoading: configLoading } = usePluginConfigWithSchema(
      isExpanded ? plugin.name : "",
    );
    const updateConfig = useUpdatePluginConfig();

    const handleSaveConfig = (newConfig: Record<string, unknown>) => {
      updateConfig.mutate(
        { name: plugin.name, config: newConfig },
        {
          onSuccess: () => toast.success(t('toast.configSaved', { defaultValue: 'Settings saved' })),
          onError: () => toast.error(t('toast.configSaveFailed', { defaultValue: 'Failed to save settings' })),
        },
      );
    };

    // Schema cast (backend returns generic Record, we know it's JSON Schema)
    const schema = configData?.schema as {
      type: "object";
      properties: Record<string, { type: "string" | "number" | "integer" | "boolean"; title?: string; description?: string; enum?: string[]; default?: unknown; minimum?: number; maximum?: number }>;
      required?: string[];
    } | null;

    return (
      <div className={cn(
        "rounded-lg border bg-card/60 backdrop-blur-md transition-all duration-300",
        plugin.status === "error" && "border-destructive/50",
        isExpanded && "border-primary bg-primary/5",
        !isExpanded && "border-border/50 hover:border-border"
      )}>
        <div
          className="p-4 cursor-pointer"
          role="button"
          tabIndex={0}
          onClick={() => setExpandedPlugin(isExpanded ? null : plugin.name)}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setExpandedPlugin(isExpanded ? null : plugin.name); } }}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="p-2 rounded-lg bg-primary/10">
                <PluginIcon className="w-5 h-5 text-primary" aria-hidden="true" />
              </div>
              <div>
                <p className="font-medium">{plugin.display_name}</p>
                <div className="flex items-center gap-2 mt-1">
                  <Badge variant="outline" className={getCategoryColor(plugin.category)}>
                    {plugin.category}
                  </Badge>
                  <span className="text-xs text-muted-foreground">v{plugin.version}</span>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-3">
              {getPluginStatusIndicator(plugin.status)}
              <Badge variant="outline" className={getHealthColor(plugin.health)}>
                {plugin.health}
              </Badge>
              <div className={cn(
                "transition-transform duration-300",
                isExpanded && "rotate-180"
              )}>
                <ChevronDown className="w-4 h-4 text-muted-foreground" aria-hidden="true" />
              </div>
            </div>
          </div>
        </div>

        <div
          className={cn(
            "grid transition-all duration-500 ease-out",
            isExpanded ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"
          )}
        >
          <div className="overflow-hidden">
            <div className="px-4 pb-4 pt-2 border-t border-border/50 space-y-4">
              {/* Quick Toggle */}
              <div className="flex items-center justify-between">
                <Label className="text-sm">{t('config.pluginEnabled')}</Label>
                <Switch
                  checked={plugin.status === "enabled"}
                  onCheckedChange={(checked) => void togglePlugin(plugin.name, checked)}
                  disabled={togglingPlugin === plugin.name || plugin.status === "missing"}
                />
              </div>

              {/* Settings Section — schema-driven form */}
              {plugin.has_config && (
                <div className="space-y-3 pt-3 border-t border-border/30">
                  <h4 className="text-sm font-medium text-muted-foreground">{t('config.configuration')}</h4>

                  {/* Icon chooser — first in settings */}
                  <div className="space-y-1.5">
                    <Label className="text-sm">Icon</Label>
                    <IconChooser
                      value={(configData?.config?.icon as string) ?? undefined}
                      onChange={(iconName) => {
                        handleSaveConfig({ ...(configData?.config ?? {}), icon: iconName });
                      }}
                    />
                  </div>

                  {configLoading ? (
                    <div className="flex items-center gap-2 text-sm text-muted-foreground py-2">
                      <Loader2 className="w-4 h-4 motion-safe:animate-spin" />
                      Loading settings...
                    </div>
                  ) : schema && schema.properties && Object.keys(schema.properties).length > 0 ? (
                    <PluginSettingsForm
                      pluginName={plugin.name}
                      schema={schema}
                      config={configData?.config ?? {}}
                      onSave={handleSaveConfig}
                      isSaving={updateConfig.isPending}
                    />
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      No additional settings available.
                    </p>
                  )}
                </div>
              )}

              {/* Actions */}
              <div className="flex gap-2 pt-3 border-t border-border/30">
                <Button variant="outline" size="sm">
                  <RefreshCw className="w-4 h-4 mr-2" aria-hidden="true" />
                  {t('actions.restart')}
                </Button>
                <Button variant="outline" size="sm">
                  <Settings className="w-4 h-4 mr-2" aria-hidden="true" />
                  {t('actions.advanced')}
                </Button>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="p-6 space-y-6 h-full overflow-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-foreground flex items-center gap-2">
            <Puzzle className="w-6 h-6" aria-hidden="true" /> {t('page.title')}
          </h1>
          <p className="text-muted-foreground">{t('page.subtitle')}</p>
        </div>
      </div>

      {/* .dryadepkg Import Section */}
      <div className="mb-6">
        <h3 className="text-lg font-medium mb-1 flex items-center gap-2">
          <PackageOpen className="w-5 h-5 text-muted-foreground" aria-hidden="true" />
          {t('page.installPackage')}
        </h3>
        <p className="text-sm text-muted-foreground mb-3">
          Download a plugin from the marketplace, then drag-and-drop or select the{" "}
          <code className="font-mono text-xs bg-muted px-1 py-0.5 rounded">.dryadepkg</code>{" "}
          file to import it.
        </p>
        <PluginImportDropzone />
      </div>

      <Tabs defaultValue="plugins" className="space-y-4" onValueChange={setActiveTab}>
        <div className="flex items-center justify-between gap-4">
          <TabsList className="bg-muted/50">
            <TabsTrigger value="plugins" className="flex items-center gap-1.5">
              <Puzzle className="w-3.5 h-3.5" aria-hidden="true" />
              {t('tabs.plugins')}
            </TabsTrigger>
            <TabsTrigger value="marketplace" className="flex items-center gap-1.5">
              <Store className="w-3.5 h-3.5" aria-hidden="true" />
              {t('tabs.marketplace')}
            </TabsTrigger>
          </TabsList>

          {activeTab === "plugins" && (
            <div className="flex items-center gap-3">
              <div className="relative w-64">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" aria-hidden="true" />
                <Input
                  placeholder={t('search.plugins')}
                  aria-label="Search plugins"
                  className="pl-10 h-9"
                  value={pluginSearch}
                  onChange={(e) => setPluginSearch(e.target.value)}
                />
              </div>
              <span className="text-sm text-muted-foreground whitespace-nowrap">
                {t('status.installed', { count: filteredPlugins.length })}
              </span>
              <CheckForUpdatesButton />
            </div>
          )}
        </div>

        {/* Plugins Tab - Full width list with inline expansion */}
        <TabsContent value="plugins" className="space-y-6 mt-4">

          {/* Plugins list */}
          <div>
            {isLoading ? (
              <div className="text-center py-12 text-muted-foreground">
                <RefreshCw className="w-6 h-6 mx-auto mb-3 motion-safe:animate-spin" />
                <p>{t('status.loadingPlugins')}</p>
              </div>
            ) : isCommunityMode ? (
              <MarketplaceTeaser t={t} />
            ) : (
              <>
                <div className="space-y-3">
                  {filteredPlugins.map((plugin) => (
                    <PluginListItem key={plugin.name} plugin={plugin} />
                  ))}
                </div>

                {filteredPlugins.length === 0 && (
                  <div className="text-center py-12 text-muted-foreground">
                    <Puzzle className="w-12 h-12 mx-auto mb-4 opacity-50" />
                    <p>{t('empty.noPluginsFound')}</p>
                  </div>
                )}
              </>
            )}
          </div>
        </TabsContent>

        {/* Marketplace Tab */}
        <TabsContent value="marketplace" className="space-y-4 mt-4">
          {/* Search and category filter bar */}
          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
            <div className="relative w-full sm:w-72">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" aria-hidden="true" />
              <Input
                placeholder={t('search.marketplace')}
                aria-label="Search marketplace"
                className="pl-10 h-9"
                value={marketplaceSearch}
                onChange={(e) => setMarketplaceSearch(e.target.value)}
              />
            </div>
            <div className="flex gap-1.5 flex-wrap">
              <Button
                variant={selectedCategory === "all" ? "default" : "outline"}
                size="sm"
                className="h-7 text-xs"
                onClick={() => setSelectedCategory("all")}
              >
                {t('marketplace.all')}
              </Button>
              {categories.map((cat) => (
                <Button
                  key={cat}
                  variant={selectedCategory === cat ? "default" : "outline"}
                  size="sm"
                  className="h-7 text-xs"
                  onClick={() => setSelectedCategory(cat)}
                >
                  {cat.replace("_", " ")}
                </Button>
              ))}
            </div>
            <span className="text-xs text-muted-foreground ml-auto whitespace-nowrap">
              {t('marketplace.pluginCount', { count: filteredMarketplace.length })}
            </span>
          </div>

          {/* Loading skeleton */}
          {marketplaceLoading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {Array.from({ length: 6 }).map((_, i) => (
                <SkeletonCard key={i} />
              ))}
            </div>
          ) : filteredMarketplace.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {filteredMarketplace.map((plugin) => (
                <MarketplaceCard
                  key={plugin.name}
                  plugin={plugin}
                  installingName={installingPlugin}
                  onInstall={handleInstall}
                  t={t}
                />
              ))}
            </div>
          ) : (
            <div className="text-center py-12 text-muted-foreground">
              <Store className="w-12 h-12 mx-auto mb-4 opacity-50" />
              <p className="font-medium text-foreground">{t('marketplace.noPluginsFound')}</p>
              <p className="text-sm mt-1">{t('marketplace.noPluginsHint')}</p>
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default PluginsPage;
