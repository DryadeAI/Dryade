// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
/**
 * Models section - extracted from SettingsPage.
 * This component receives all model-related state and handlers as props
 * to avoid duplicating the complex model configuration logic.
 */
import { useState } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Brain, Database, Mic, Eye as EyeIcon, Loader2, Plus, Check, RefreshCw } from "lucide-react";
import type { ModelsConfig, ModelCapability, ProviderWithCapabilities, ProviderParamsResponse, InferenceParams } from "@/types/extended-api";
import { InferenceParamsSection } from "./InferenceParamsSection";

interface ModelsSectionProps {
  modelConfig: ModelsConfig | null;
  modelConfigLoading: boolean;
  registryProviders: ProviderWithCapabilities[];
  discoveredModels: Record<string, string[]>;
  discoveringModels: string | null;
  customEndpoints: Record<string, string>;
  customAsrEndpoints: Record<string, string>;
  customEmbeddingEndpoints: Record<string, string>;
  hasUnsavedChanges: Record<ModelCapability, boolean>;
  testingProvider: string | null;
  onModelConfigChange: (capability: ModelCapability, field: "provider" | "model", value: string) => void;
  onSaveModelConfig: (capability: ModelCapability) => void;
  onEndpointChange: (provider: string, endpoint: string, capability?: ModelCapability) => void;
  onTestConnection: (provider: string, capability?: ModelCapability) => void;
  onFetchModels: (provider: string, capability?: ModelCapability) => void;
  onCreateCustomProvider: (form: { display_name: string; base_url: string; requires_api_key: boolean; capabilities: string[] }) => void;
  providerParamsData: ProviderParamsResponse | null;
  inferenceParams: Record<ModelCapability, InferenceParams>;
  vllmServerParams: InferenceParams;
  onInferenceParamsChange: (capability: ModelCapability, params: InferenceParams) => void;
  onVllmServerParamsChange: (params: InferenceParams) => void;
  onResetInferenceParams: (capability: ModelCapability) => void;
  getProvidersForCapability: (capability: ModelCapability) => ProviderWithCapabilities[];
  supportsCustomEndpoint: (provider: string) => boolean;
  hasApiKey: (provider: string) => boolean;
}

export const ModelsSection = (props: ModelsSectionProps) => {
  const {
    modelConfig, modelConfigLoading, registryProviders, discoveredModels, discoveringModels,
    customEndpoints, customAsrEndpoints, customEmbeddingEndpoints, hasUnsavedChanges, testingProvider,
    onModelConfigChange, onSaveModelConfig, onEndpointChange, onTestConnection, onFetchModels,
    onCreateCustomProvider, providerParamsData, inferenceParams, vllmServerParams,
    onInferenceParamsChange, onVllmServerParamsChange, onResetInferenceParams,
    getProvidersForCapability, supportsCustomEndpoint, hasApiKey,
  } = props;

  const [showAddProviderDialog, setShowAddProviderDialog] = useState(false);
  const [addingProvider, setAddingProvider] = useState(false);
  const [newProviderForm, setNewProviderForm] = useState({
    display_name: "", base_url: "", requires_api_key: false, capabilities: [] as string[],
  });

  const handleCreateProvider = async () => {
    setAddingProvider(true);
    try {
      await onCreateCustomProvider(newProviderForm);
      setShowAddProviderDialog(false);
      setNewProviderForm({ display_name: "", base_url: "", requires_api_key: false, capabilities: [] });
    } finally {
      setAddingProvider(false);
    }
  };

  const renderCapabilityCard = (capability: ModelCapability, label: string, icon: React.ElementType) => {
    const Icon = icon;
    if (!modelConfig) return null;
    return (
      <div key={capability} className="rounded-lg border border-border bg-card p-4 space-y-4 shadow-sm">
        <div className="flex items-center gap-2">
          <Icon className="w-4 h-4 text-primary" />
          <span className="font-medium text-sm">{label}</span>
          {modelConfig[capability]?.model && (
            <Badge variant="secondary" className="text-xs ml-auto">{modelConfig[capability].model}</Badge>
          )}
        </div>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label className="text-xs">Provider</Label>
            <div className="flex gap-2">
              <Select
                value={modelConfig[capability]?.provider ?? ""}
                onValueChange={(value) => onModelConfigChange(capability, "provider", value)}
              >
                <SelectTrigger className="flex-1 h-9 text-sm"><SelectValue placeholder="Select provider" /></SelectTrigger>
                <SelectContent>
                  {getProvidersForCapability(capability).map((provider) => (
                    <SelectItem key={provider.name} value={provider.name}>
                      <div className="flex items-center gap-2">
                        {provider.display_name}
                        {provider.is_custom && <Badge variant="secondary" className="text-xs">Custom</Badge>}
                        {provider.requires_api_key && !hasApiKey(provider.name) && <Badge variant="outline" className="text-xs">Key required</Badge>}
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button variant="outline" size="icon" className="h-9 w-9 shrink-0" onClick={() => setShowAddProviderDialog(true)}>
                <Plus className="w-4 h-4" />
              </Button>
            </div>
          </div>

          {modelConfig[capability]?.provider && supportsCustomEndpoint(modelConfig[capability].provider) && (
            <div className="space-y-1.5">
              <Label className="text-xs">Endpoint URL</Label>
              <Input
                type="url" placeholder="http://localhost:11434" className="h-9 text-sm"
                value={capability === "audio" ? customAsrEndpoints[modelConfig[capability].provider] || "" : capability === "embedding" ? customEmbeddingEndpoints[modelConfig[capability].provider] || "" : customEndpoints[modelConfig[capability].provider] || ""}
                onChange={(e) => onEndpointChange(modelConfig[capability].provider, e.target.value, capability)}
              />
            </div>
          )}

          <div className="space-y-1.5">
            <Label className="text-xs">Model</Label>
            <div className="flex gap-2">
              <Select
                value={modelConfig[capability]?.model ?? ""}
                onValueChange={(value) => onModelConfigChange(capability, "model", value)}
                disabled={!modelConfig[capability]?.provider || discoveringModels === modelConfig[capability]?.provider}
              >
                <SelectTrigger className="flex-1 h-9 text-sm">
                  {discoveringModels === modelConfig[capability]?.provider ? (
                    <div className="flex items-center gap-2"><Loader2 className="w-3 h-3 animate-spin" /><span>Discovering...</span></div>
                  ) : (
                    <SelectValue placeholder="Select model" />
                  )}
                </SelectTrigger>
                <SelectContent>
                  {(discoveredModels[modelConfig[capability]?.provider ?? ""] || []).map((model) => (
                    <SelectItem key={model} value={model}>{model}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button variant="outline" size="icon" className="h-9 w-9 shrink-0"
                onClick={() => onFetchModels(modelConfig[capability]?.provider, capability)}
                disabled={!modelConfig[capability]?.provider || discoveringModels === modelConfig[capability]?.provider}
              >
                <RefreshCw className={cn("w-3 h-3", discoveringModels === modelConfig[capability]?.provider && "animate-spin")} />
              </Button>
            </div>
          </div>

          {modelConfig[capability]?.provider && (
            <>
              <div className="flex gap-2 pt-1">
                <Button variant="outline" size="sm" className="flex-1 text-xs h-8"
                  onClick={() => onTestConnection(modelConfig[capability].provider, capability)}
                  disabled={testingProvider === modelConfig[capability].provider}
                >
                  {testingProvider === modelConfig[capability].provider ? <><Loader2 className="w-3 h-3 mr-1 animate-spin" />Testing...</> : "Test"}
                </Button>
                <Button size="sm" className="flex-1 text-xs h-8"
                  onClick={() => onSaveModelConfig(capability)}
                  disabled={!hasUnsavedChanges[capability] || !modelConfig[capability]?.model}
                >
                  {hasUnsavedChanges[capability] ? <><Check className="w-3 h-3 mr-1" />Save</> : "Saved"}
                </Button>
              </div>
              {providerParamsData && (() => {
                const provider = modelConfig[capability].provider;
                const providerSupported = providerParamsData.provider_params[provider] || [];
                const capabilitySupported = providerParamsData.capability_support[capability] || [];
                const supportedParams = providerSupported.filter(p => capabilitySupported.includes(p));
                if (supportedParams.length === 0) return null;
                return (
                  <InferenceParamsSection
                    capability={capability}
                    provider={provider}
                    params={inferenceParams[capability]}
                    supportedParams={supportedParams}
                    paramSpecs={providerParamsData.param_specs}
                    presets={providerParamsData.presets}
                    vllmServerParams={capability === "llm" ? vllmServerParams : undefined}
                    vllmServerParamSpecs={capability === "llm" && provider === "vllm" ? providerParamsData.vllm_server_params : undefined}
                    onParamsChange={(params) => onInferenceParamsChange(capability, params)}
                    onVllmServerParamsChange={capability === "llm" ? onVllmServerParamsChange : undefined}
                    onReset={() => onResetInferenceParams(capability)}
                  />
                );
              })()}
            </>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-4">
      {modelConfigLoading ? (
        <div className="flex items-center justify-center py-8"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>
      ) : !modelConfig ? (
        <div className="text-center py-8 text-muted-foreground">Model configuration not available.</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {renderCapabilityCard("llm", "LLM", Brain)}
          {renderCapabilityCard("embedding", "Embedding", Database)}
          {renderCapabilityCard("audio", "Audio", Mic)}
          {renderCapabilityCard("vision", "Vision", EyeIcon)}
        </div>
      )}

      <Dialog open={showAddProviderDialog} onOpenChange={setShowAddProviderDialog}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Add Custom Provider</DialogTitle>
            <DialogDescription>Add an OpenAI-compatible provider endpoint.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>Display Name</Label>
              <Input placeholder="My LLM Server" value={newProviderForm.display_name} onChange={(e) => setNewProviderForm((f) => ({ ...f, display_name: e.target.value }))} />
            </div>
            <div className="space-y-2">
              <Label>Base URL</Label>
              <Input type="url" placeholder="http://localhost:8080/v1" value={newProviderForm.base_url} onChange={(e) => setNewProviderForm((f) => ({ ...f, base_url: e.target.value }))} />
            </div>
            <div className="flex items-center gap-2">
              <Switch checked={newProviderForm.requires_api_key} onCheckedChange={(checked) => setNewProviderForm((f) => ({ ...f, requires_api_key: checked }))} />
              <Label>Requires API Key</Label>
            </div>
            <div className="space-y-2">
              <Label>Capabilities</Label>
              <div className="flex flex-wrap gap-3">
                {[{ id: "llm", label: "LLM" }, { id: "embedding", label: "Embedding" }, { id: "audio_asr", label: "Audio ASR" }, { id: "audio_tts", label: "Audio TTS" }, { id: "vision", label: "Vision" }].map((cap) => (
                  <label key={cap.id} className="flex items-center gap-1.5 cursor-pointer">
                    <Checkbox checked={newProviderForm.capabilities.includes(cap.id)} onCheckedChange={(checked) => {
                      setNewProviderForm((f) => ({ ...f, capabilities: checked ? [...f.capabilities, cap.id] : f.capabilities.filter((c) => c !== cap.id) }));
                    }} />
                    <span className="text-sm">{cap.label}</span>
                  </label>
                ))}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAddProviderDialog(false)}>Cancel</Button>
            <Button onClick={handleCreateProvider} disabled={addingProvider || !newProviderForm.display_name || !newProviderForm.base_url || newProviderForm.capabilities.length === 0}>
              {addingProvider && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}Add Provider
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
