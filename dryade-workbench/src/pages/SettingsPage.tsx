// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useEffect, useState, useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useDebouncedCallback } from "use-debounce";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Loader2, User, Palette, Bell, MessageSquare, Cpu, Key, Database, Factory, ChevronLeft, Menu, Search, X } from "lucide-react";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { useIsMobile } from "@/hooks/use-mobile";
import { PluginSlot } from "@/plugins/slots";
import { toast } from "sonner";
import { usersApi, modelsConfigApi, providerRegistryApi, customProvidersApi } from "@/services/api";
import { useAuth } from "@/contexts/AuthContext";
import type {
  AppSettings, ApiKey, User as UserType, ModelsConfig, ProviderInfo,
  ApiKeyInfo, ModelCapability, ProviderWithCapabilities,
  ProviderParamsResponse, InferenceParams,
} from "@/types/extended-api";

import { ProfileSection } from "@/components/settings/ProfileSection";
import { AppearanceSection } from "@/components/settings/AppearanceSection";
import { NotificationsSection } from "@/components/settings/NotificationsSection";
import { ChatAgentsSection } from "@/components/settings/ChatAgentsSection";
import { ModelsSection } from "@/components/settings/ModelsSection";
import { ApiKeysSection } from "@/components/settings/ApiKeysSection";
import { DataPrivacySection } from "@/components/settings/DataPrivacySection";
import { FactorySection } from "@/components/settings/FactorySection";

// --- Nav config ---
type SettingsCategory = "profile" | "appearance" | "notifications" | "chat" | "models" | "api-keys" | "data" | "factory";

interface NavItem {
  id: SettingsCategory;
  label: string;
  icon: React.ElementType;
  description: string;
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

const useNavGroups = (): NavGroup[] => {
  const { t } = useTranslation('settings');
  return useMemo(() => [
    {
      label: t('groups.account'),
      items: [
        { id: "profile", label: t('tabs.profile'), icon: User, description: t('tabs.profileDesc') },
        { id: "appearance", label: t('tabs.appearance'), icon: Palette, description: t('tabs.appearanceDesc') },
        { id: "notifications", label: t('tabs.notifications'), icon: Bell, description: t('tabs.notificationsDesc') },
      ],
    },
    {
      label: t('groups.workspace'),
      items: [
        { id: "chat", label: t('tabs.chat'), icon: MessageSquare, description: t('tabs.chatDesc') },
        { id: "models", label: t('tabs.models'), icon: Cpu, description: t('tabs.modelsDesc') },
        { id: "api-keys", label: t('tabs.apiKeys'), icon: Key, description: t('tabs.apiKeysDesc') },
        { id: "factory", label: t('tabs.factory'), icon: Factory, description: t('tabs.factoryDesc') },
      ],
    },
    {
      label: t('groups.advanced'),
      items: [
        { id: "data", label: t('tabs.data'), icon: Database, description: t('tabs.dataDesc') },
      ],
    },
  ], [t]);
};

const ALL_ITEMS_STATIC = [
  "profile", "appearance", "notifications", "chat", "models", "api-keys", "factory", "data"
] as SettingsCategory[];

const DEFAULT_ENDPOINTS: Record<string, string> = {
  ollama: "http://localhost:11434",
  vllm: "http://localhost:8000/v1",
  azure_openai: "",
  local: "http://localhost:8000/v1",
};

// --- Sidebar Nav Component ---
const SettingsNav = ({
  activeId,
  onSelect,
}: {
  activeId: SettingsCategory;
  onSelect: (id: SettingsCategory) => void;
}) => {
  const navGroups = useNavGroups();
  const [searchQuery, setSearchQuery] = useState("");

  const filteredGroups = useMemo(() => {
    if (!searchQuery.trim()) return navGroups;
    const q = searchQuery.toLowerCase();
    return navGroups
      .map((group) => ({
        ...group,
        items: group.items.filter(
          (item) =>
            item.label.toLowerCase().includes(q) ||
            item.description.toLowerCase().includes(q)
        ),
      }))
      .filter((group) => group.items.length > 0);
  }, [navGroups, searchQuery]);

  return (
    <nav className="py-4 px-3 space-y-4">
      <div className="px-3 relative">
        <Search aria-hidden="true" className="absolute left-5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
        <input
          type="text"
          placeholder="Search settings..."
          aria-label="Search settings"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full h-8 pl-8 pr-8 text-xs rounded-md border border-border bg-secondary/30 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary/40"
        />
        {searchQuery && (
          <button
            onClick={() => setSearchQuery("")}
            aria-label="Clear search"
            className="absolute right-5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          >
            <X aria-hidden="true" className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
      <div className="space-y-6">
        {filteredGroups.map((group) => (
          <div key={group.label}>
            <p className="text-[11px] font-semibold text-muted-foreground tracking-wider uppercase px-3 mb-2">
              {group.label}
            </p>
            <div className="space-y-0.5">
              {group.items.map((item) => {
                const isActive = activeId === item.id;
                return (
                  <button
                    key={item.id}
                    onClick={() => onSelect(item.id)}
                    className={cn(
                      "w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-sm transition-colors min-h-[40px]",
                      isActive
                        ? "bg-primary/10 text-primary font-semibold"
                        : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                    )}
                  >
                    <item.icon aria-hidden="true" className="w-4 h-4 shrink-0" />
                    <span>{item.label}</span>
                  </button>
                );
              })}
            </div>
          </div>
        ))}
        {filteredGroups.length === 0 && (
          <p className="text-xs text-muted-foreground text-center py-4">No matching settings</p>
        )}
      </div>
    </nav>
  );
};

// --- Main Component ---
const SettingsPage = () => {
  const { user: authUser, isLoading: authLoading, refreshUser } = useAuth();
  const isMobile = useIsMobile();
  const navGroups = useNavGroups();
  const [activeCategory, setActiveCategory] = useState<SettingsCategory>("profile");
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [mobileShowContent, setMobileShowContent] = useState(false);

  // --- All existing state (preserved) ---
  const [settings, setSettings] = useState<AppSettings>({
    appearance: { theme: "dark", sidebar_collapsed: false, compact_mode: false, font_size: "medium" },
    notifications: {
      email_enabled: true,
      email_categories: { workflow_complete: true, plan_approval: true, system_alerts: true, weekly_digest: false },
      sound_enabled: true, desktop_enabled: false,
    },
    chat: { default_mode: "chat", auto_scroll: true, show_timestamps: true, syntax_theme: "github", expand_reasoning: false },
    data: { auto_save: true, save_interval_seconds: 30 },
  });
  const [apiKeys] = useState<ApiKey[]>([]);
  const [modelConfig, setModelConfig] = useState<ModelsConfig | null>(null);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [providerApiKeys, setProviderApiKeys] = useState<ApiKeyInfo[]>([]);
  const [modelConfigLoading, setModelConfigLoading] = useState(false);
  const [registryProviders, setRegistryProviders] = useState<ProviderWithCapabilities[]>([]);
  const [customEndpoints, setCustomEndpoints] = useState<Record<string, string>>({});
  const [customAsrEndpoints, setCustomAsrEndpoints] = useState<Record<string, string>>({});
  const [customEmbeddingEndpoints, setCustomEmbeddingEndpoints] = useState<Record<string, string>>({});
  const [discoveredModels, setDiscoveredModels] = useState<Record<string, string[]>>({});
  const [discoveringModels, setDiscoveringModels] = useState<string | null>(null);
  const [testingProvider, setTestingProvider] = useState<string | null>(null);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState<Record<ModelCapability, boolean>>({
    llm: false, embedding: false, audio: false, vision: false,
  });
  const [providerParamsData, setProviderParamsData] = useState<ProviderParamsResponse | null>(null);
  const [inferenceParams, setInferenceParams] = useState<Record<ModelCapability, InferenceParams>>({
    llm: {}, embedding: {}, audio: {}, vision: {},
  });
  const [vllmServerParams, setVllmServerParams] = useState<InferenceParams>({});

  const user = useMemo<UserType | null>(() => {
    if (!authUser) return null;
    return {
      id: authUser.id, email: authUser.email, display_name: authUser.display_name,
      avatar_color: (authUser.preferences?.avatar_color as string | undefined) ?? "#2BAB38",
      role: authUser.role === "admin" ? "admin" : "member",
      is_external: authUser.is_external, first_seen: authUser.first_seen, last_seen: authUser.last_seen,
    };
  }, [authUser]);

  // --- Model config loading ---
  useEffect(() => {
    const loadModelConfig = async () => {
      try {
        setModelConfigLoading(true);
        const [configRes, providersRes, keysRes, registryRes, providerParamsRes] = await Promise.all([
          modelsConfigApi.getConfig(), modelsConfigApi.getProviders(), modelsConfigApi.getApiKeys(),
          providerRegistryApi.listProviders().catch(() => []),
          modelsConfigApi.getProviderParams().catch(() => null),
        ]);
        setModelConfig(configRes); setProviders(providersRes); setProviderApiKeys(keysRes); setRegistryProviders(registryRes);
        if (providerParamsRes) setProviderParamsData(providerParamsRes);
        setInferenceParams({
          llm: configRes.llm_inference_params || {},
          embedding: configRes.embedding_inference_params || {},
          audio: configRes.audio_inference_params || {},
          vision: configRes.vision_inference_params || {},
        });
        setVllmServerParams(configRes.vllm_server_params || {});
        const endpoints: Record<string, string> = {};
        const asrEndpoints: Record<string, string> = {};
        const embeddingEndpoints: Record<string, string> = {};
        registryRes.forEach((provider) => {
          if (provider.supports_custom_endpoint) {
            if (configRes.llm_endpoint && configRes.llm.provider === provider.name) endpoints[provider.name] = configRes.llm_endpoint;
            else if (provider.is_custom && provider.base_url) endpoints[provider.name] = provider.base_url;
            else if (DEFAULT_ENDPOINTS[provider.name]) endpoints[provider.name] = DEFAULT_ENDPOINTS[provider.name];
            if (configRes.asr_endpoint && configRes.audio.provider === provider.name) asrEndpoints[provider.name] = configRes.asr_endpoint;
            else if (provider.is_custom && provider.base_url) asrEndpoints[provider.name] = provider.base_url;
            else if (DEFAULT_ENDPOINTS[provider.name]) asrEndpoints[provider.name] = DEFAULT_ENDPOINTS[provider.name];
            if (configRes.embedding_endpoint && configRes.embedding.provider === provider.name) embeddingEndpoints[provider.name] = configRes.embedding_endpoint;
            else if (provider.is_custom && provider.base_url) embeddingEndpoints[provider.name] = provider.base_url;
            else if (DEFAULT_ENDPOINTS[provider.name]) embeddingEndpoints[provider.name] = DEFAULT_ENDPOINTS[provider.name];
          }
        });
        setCustomEndpoints(endpoints); setCustomAsrEndpoints(asrEndpoints); setCustomEmbeddingEndpoints(embeddingEndpoints);
      } catch (error) { console.error("Failed to load model config:", error); }
      finally { setModelConfigLoading(false); }
    };
    loadModelConfig();
  }, []);

  // --- Model handlers (preserved) ---
  const fetchModelsForProvider = useCallback(
    async (providerName: string, capability?: ModelCapability) => {
      if (!providerName) return;
      const rp = registryProviders.find((p) => p.name === providerName);
      const needsEndpoint = rp?.supports_custom_endpoint;
      const endpointValue = capability === "audio" ? customAsrEndpoints[providerName] : capability === "embedding" ? customEmbeddingEndpoints[providerName] : customEndpoints[providerName];
      if (needsEndpoint && !endpointValue) { toast.warning(`Enter an endpoint URL for ${rp?.display_name || providerName} to discover models.`); return; }
      if (rp?.requires_api_key && !providerApiKeys.some((k) => k.provider === providerName)) return;
      setDiscoveringModels(providerName);
      try {
        const endpoint = capability === "audio" ? customAsrEndpoints[providerName] : capability === "embedding" ? customEmbeddingEndpoints[providerName] : customEndpoints[providerName];
        const result = await providerRegistryApi.discoverModels(providerName, endpoint);
        if (result.models?.length) { setDiscoveredModels((prev) => ({ ...prev, [providerName]: result.models })); toast.success(`Found ${result.models.length} models`); }
        else { toast.warning(`No models found. Check endpoint or try again.`); }
      } catch { toast.error(`Could not discover models`); }
      finally { setDiscoveringModels(null); }
    }, [registryProviders, customEndpoints, customAsrEndpoints, customEmbeddingEndpoints, providerApiKeys]
  );

  const handleModelConfigChange = useCallback(
    (capability: ModelCapability, field: "provider" | "model", value: string) => {
      if (!modelConfig) return;
      const currentConfig = modelConfig[capability] || { provider: "", model: "" };
      const newConfig = { ...currentConfig, [field]: value };
      if (field === "provider") { newConfig.model = ""; fetchModelsForProvider(value, capability); }
      setModelConfig({ ...modelConfig, [capability]: newConfig });
      setHasUnsavedChanges(prev => ({ ...prev, [capability]: true }));
    }, [modelConfig, fetchModelsForProvider]
  );

  const supportsCustomEndpoint = useCallback((providerName: string) => {
    return registryProviders.find((p) => p.name === providerName)?.supports_custom_endpoint ?? false;
  }, [registryProviders]);

  const hasApiKey = useCallback((providerName: string) => {
    return providerApiKeys.some((k) => k.provider === providerName);
  }, [providerApiKeys]);

  const handleSaveModelConfig = useCallback(
    async (capability: ModelCapability) => {
      if (!modelConfig) return;
      const config = modelConfig[capability];
      if (!config?.provider || !config?.model) { toast.error("Please select both a provider and a model"); return; }
      try {
        const hasEndpoint = supportsCustomEndpoint(config.provider);
        let configWithEndpoint: typeof config & { endpoint?: string | null };
        if (capability === "llm") configWithEndpoint = { ...config, endpoint: hasEndpoint ? (customEndpoints[config.provider] || null) : null };
        else if (capability === "audio") configWithEndpoint = { ...config, endpoint: hasEndpoint ? (customAsrEndpoints[config.provider] || null) : null };
        else if (capability === "embedding") configWithEndpoint = { ...config, endpoint: hasEndpoint ? (customEmbeddingEndpoints[config.provider] || null) : null };
        else configWithEndpoint = config;
        const updated = await modelsConfigApi.updateConfig(
          capability,
          configWithEndpoint,
          inferenceParams[capability],
          capability === 'llm' ? vllmServerParams : undefined
        );
        setModelConfig(updated); setHasUnsavedChanges(prev => ({ ...prev, [capability]: false })); toast.success("Configuration saved");
      } catch (error) { toast.error(error instanceof Error ? error.message : "Failed to save configuration"); }
    }, [modelConfig, customEndpoints, customAsrEndpoints, customEmbeddingEndpoints, supportsCustomEndpoint, inferenceParams, vllmServerParams]
  );

  const debouncedDiscoverModels = useDebouncedCallback(
    async (provider: string, endpoint: string) => {
      if (!endpoint.trim()) return;
      setDiscoveringModels(provider);
      try {
        const result = await providerRegistryApi.discoverModels(provider, endpoint);
        if (result.models?.length) { setDiscoveredModels((prev) => ({ ...prev, [provider]: result.models })); }
      } catch { /* silent */ }
      finally { setDiscoveringModels(null); }
    }, 800
  );

  const handleEndpointChange = useCallback((provider: string, endpoint: string, capability?: ModelCapability) => {
    if (capability === "audio") setCustomAsrEndpoints((prev) => ({ ...prev, [provider]: endpoint }));
    else if (capability === "embedding") setCustomEmbeddingEndpoints((prev) => ({ ...prev, [provider]: endpoint }));
    else setCustomEndpoints((prev) => ({ ...prev, [provider]: endpoint }));
    debouncedDiscoverModels(provider, endpoint);
    if (capability) setHasUnsavedChanges(prev => ({ ...prev, [capability]: true }));
  }, [debouncedDiscoverModels]);

  const handleInferenceParamsChange = useCallback((capability: ModelCapability, params: InferenceParams) => {
    setInferenceParams(prev => ({ ...prev, [capability]: params }));
    setHasUnsavedChanges(prev => ({ ...prev, [capability]: true }));
  }, []);

  const handleVllmServerParamsChange = useCallback((params: InferenceParams) => {
    setVllmServerParams(params);
    setHasUnsavedChanges(prev => ({ ...prev, llm: true }));
  }, []);

  const handleResetInferenceParams = useCallback((capability: ModelCapability) => {
    if (!providerParamsData) return;
    const defaults: InferenceParams = {};
    for (const [name, spec] of Object.entries(providerParamsData.param_specs)) {
      defaults[name] = spec.default;
    }
    setInferenceParams(prev => ({ ...prev, [capability]: defaults }));
    setHasUnsavedChanges(prev => ({ ...prev, [capability]: true }));
  }, [providerParamsData]);

  const handleTestConnection = useCallback(async (provider: string, capability?: ModelCapability) => {
    setTestingProvider(provider);
    try {
      const endpoint = capability === "audio" ? customAsrEndpoints[provider] : capability === "embedding" ? customEmbeddingEndpoints[provider] : customEndpoints[provider];
      const result = await providerRegistryApi.testConnection(provider, endpoint);
      if (result.success) {
        if (result.models?.length) setDiscoveredModels((prev) => ({ ...prev, [provider]: result.models! }));
        toast.success(`Connection successful${result.models?.length ? ` (${result.models.length} models)` : ""}`);
      } else { toast.error(result.message || "Connection failed"); }
    } catch (error) { toast.error(error instanceof Error ? error.message : "Connection test failed"); }
    finally { setTestingProvider(null); }
  }, [customEndpoints, customAsrEndpoints, customEmbeddingEndpoints]);

  const getProvidersForCapability = useCallback((capability: ModelCapability) => {
    if (registryProviders.length > 0) {
      return registryProviders
        .filter((p) => {
          switch (capability) {
            case 'llm': return p.capabilities.llm;
            case 'embedding': return p.capabilities.embedding;
            case 'audio': return p.capabilities.audio_asr || p.capabilities.audio_tts;
            case 'vision': return p.capabilities.vision;
            default: return false;
          }
        })
        .map((p) => ({
          name: p.name, display_name: p.display_name,
          models: discoveredModels[p.name] || [],
          requires_api_key: p.requires_api_key, is_custom: p.is_custom,
          capabilities: [capability],
        }));
    }
    return (Array.isArray(providers) ? providers : []).filter((p: ProviderInfo) => p.capabilities?.includes(capability));
  }, [registryProviders, providers, discoveredModels]);

  const handleSaveProviderApiKey = useCallback(async (provider: string, key: string) => {
    try {
      await modelsConfigApi.storeApiKey(provider, key);
      const keys = await modelsConfigApi.getApiKeys();
      setProviderApiKeys(keys);
      toast.success(`API key saved for ${provider}`);
    } catch (error) { toast.error(error instanceof Error ? error.message : "Failed to save API key"); }
  }, []);

  const handleDeleteProviderApiKey = useCallback(async (provider: string) => {
    try {
      await modelsConfigApi.deleteApiKey(provider);
      const keys = await modelsConfigApi.getApiKeys();
      setProviderApiKeys(keys);
      toast.success(`API key deleted`);
    } catch (error) { toast.error(error instanceof Error ? error.message : "Failed to delete API key"); }
  }, []);

  const handleCreateCustomProvider = useCallback(async (form: { display_name: string; base_url: string; requires_api_key: boolean; capabilities: string[] }) => {
    await customProvidersApi.create(form);
    const registryRes = await providerRegistryApi.listProviders().catch(() => []);
    setRegistryProviders(registryRes);
    registryRes.forEach((p) => {
      if (p.is_custom && p.base_url && !customEndpoints[p.name]) {
        setCustomEndpoints((prev) => ({ ...prev, [p.name]: p.base_url! }));
        setCustomAsrEndpoints((prev) => ({ ...prev, [p.name]: p.base_url! }));
        setCustomEmbeddingEndpoints((prev) => ({ ...prev, [p.name]: p.base_url! }));
      }
    });
    toast.success("Custom provider added");
  }, [customEndpoints]);

  const handleDeleteCustomProvider = useCallback(async (slug: string, displayName: string) => {
    try {
      await customProvidersApi.delete(slug);
      const registryRes = await providerRegistryApi.listProviders().catch(() => []);
      setRegistryProviders(registryRes);
      toast.success(`Deleted: ${displayName}`);
    } catch (error) { toast.error(error instanceof Error ? error.message : "Failed to delete provider"); }
  }, []);

  // --- Loading / Auth guard ---
  if (authLoading) {
    return (
      <div className="h-full flex">
        <div className="flex-1 overflow-auto">
          <div className="max-w-2xl mx-auto px-8 py-8 space-y-6">
            <div className="mb-8 space-y-2">
              <Skeleton className="h-7 w-40" />
              <Skeleton className="h-4 w-64" />
            </div>
            {[80, 64, 56, 80].map((h, i) => (
              <div key={i} className="rounded-lg border border-border bg-card shadow-sm">
                <div className="px-5 py-4 border-b border-border space-y-1.5">
                  <Skeleton className="h-4 w-32" />
                  <Skeleton className="h-3 w-48" />
                </div>
                <div className="px-5 py-4 space-y-4">
                  {Array.from({ length: 3 }).map((_, j) => (
                    <div key={j} className="flex items-center justify-between py-2">
                      <Skeleton className="h-4 w-36" />
                      <Skeleton className="h-6 w-12 rounded-full" />
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="w-[240px] shrink-0 border-l border-border bg-muted/30 overflow-auto">
          <div className="px-4 pt-6 pb-2">
            <Skeleton className="h-6 w-20" />
          </div>
          <div className="py-4 px-3 space-y-4">
            {[3, 4, 1].map((count, gi) => (
              <div key={gi} className="space-y-1">
                <Skeleton className="h-3 w-16 ml-3 mb-2" />
                {Array.from({ length: count }).map((_, i) => (
                  <Skeleton key={i} className="h-9 w-full rounded-md" />
                ))}
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (!authUser || !user) {
    return (
      <div className="h-full flex flex-col items-center justify-center p-6 gap-3">
        <p className="text-muted-foreground">Unable to load your profile. Please sign in again.</p>
        <Button variant="outline" onClick={() => window.location.href = '/auth'}>Sign in</Button>
      </div>
    );
  }

  const allItems = navGroups.flatMap((g) => g.items);
  const activeItem = allItems.find((i) => i.id === activeCategory)!;

  const handleMobileSelect = (id: SettingsCategory) => {
    setActiveCategory(id);
    setMobileShowContent(true);
    setMobileNavOpen(false);
  };

  // --- Render section content ---
  const renderContent = () => {
    switch (activeCategory) {
      case "profile":
        return <ProfileSection user={user} />;
      case "appearance":
        return <AppearanceSection settings={settings} onSettingsChange={setSettings} />;
      case "notifications":
        return <NotificationsSection settings={settings} onSettingsChange={setSettings} />;
      case "chat":
        return <ChatAgentsSection settings={settings} onSettingsChange={setSettings} />;
      case "models":
        return (
          <ModelsSection
            modelConfig={modelConfig}
            modelConfigLoading={modelConfigLoading}
            registryProviders={registryProviders}
            discoveredModels={discoveredModels}
            discoveringModels={discoveringModels}
            customEndpoints={customEndpoints}
            customAsrEndpoints={customAsrEndpoints}
            customEmbeddingEndpoints={customEmbeddingEndpoints}
            hasUnsavedChanges={hasUnsavedChanges}
            testingProvider={testingProvider}
            providerParamsData={providerParamsData}
            inferenceParams={inferenceParams}
            vllmServerParams={vllmServerParams}
            onModelConfigChange={handleModelConfigChange}
            onSaveModelConfig={handleSaveModelConfig}
            onEndpointChange={handleEndpointChange}
            onTestConnection={handleTestConnection}
            onFetchModels={fetchModelsForProvider}
            onCreateCustomProvider={handleCreateCustomProvider}
            onInferenceParamsChange={handleInferenceParamsChange}
            onVllmServerParamsChange={handleVllmServerParamsChange}
            onResetInferenceParams={handleResetInferenceParams}
            getProvidersForCapability={getProvidersForCapability}
            supportsCustomEndpoint={supportsCustomEndpoint}
            hasApiKey={hasApiKey}
          />
        );
      case "api-keys":
        return (
          <ApiKeysSection
            apiKeys={apiKeys}
            providers={providers}
            registryProviders={registryProviders}
            providerApiKeys={providerApiKeys}
            testingProvider={testingProvider}
            onSaveProviderApiKey={handleSaveProviderApiKey}
            onDeleteProviderApiKey={handleDeleteProviderApiKey}
            onTestConnection={handleTestConnection}
            onDeleteCustomProvider={handleDeleteCustomProvider}
          />
        );
      case "data":
        return <DataPrivacySection settings={settings} onSettingsChange={setSettings} />;
      case "factory":
        return <FactorySection />;
      default:
        return null;
    }
  };

  // --- Mobile layout ---
  if (isMobile) {
    if (!mobileShowContent) {
      // Show category list
      return (
        <div className="h-full overflow-auto">
          <div className="px-4 pt-6 pb-4">
            <h1 className="text-2xl font-semibold text-foreground">Settings</h1>
          </div>
          <SettingsNav activeId={activeCategory} onSelect={handleMobileSelect} />
        </div>
      );
    }

    return (
      <div className="h-full overflow-auto">
        <div className="px-4 pt-4 pb-2">
          <button
            onClick={() => setMobileShowContent(false)}
            className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors mb-4"
          >
            <ChevronLeft aria-hidden="true" className="w-4 h-4" />
            Settings
          </button>
          <h1 className="text-xl font-semibold text-foreground">{activeItem.label}</h1>
          <p className="text-sm text-muted-foreground mt-0.5">{activeItem.description}</p>
        </div>
        <div className="px-4 py-4">
          {renderContent()}
          <PluginSlot name="settings-section" className="mt-6" />
        </div>
      </div>
    );
  }

  // --- Desktop layout ---
  return (
    <div className="h-full flex" data-testid="settings-container">
      {/* Content panel */}
      <div className="flex-1 overflow-auto">
        <div className="max-w-2xl mx-auto px-8 py-8">
          <div className="mb-8">
            <h1 className="text-2xl font-semibold text-foreground">{activeItem.label}</h1>
            <p className="text-sm text-muted-foreground mt-1">{activeItem.description}</p>
          </div>
          {renderContent()}
          <PluginSlot name="settings-section" className="mt-8" />
        </div>
      </div>

      {/* Right sidebar */}
      <div className="w-[240px] shrink-0 border-l border-border bg-muted/30 overflow-auto">
        <div className="px-4 pt-6 pb-2">
          <h2 className="text-lg font-semibold text-foreground">Settings</h2>
        </div>
        <SettingsNav activeId={activeCategory} onSelect={setActiveCategory} />
      </div>
    </div>
  );
};

export default SettingsPage;
