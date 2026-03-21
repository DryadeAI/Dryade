// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Plus, Trash2, Copy, Eye, EyeOff, Loader2, Brain, Database, Mic, Eye as EyeIcon } from "lucide-react";
import { SettingsCard, SettingRow } from "./SettingsCard";
import { toast } from "sonner";
import type { ApiKey, ApiKeyInfo, ProviderWithCapabilities, ProviderInfo } from "@/types/extended-api";
import { ProviderFallbackOrder } from "./ProviderFallbackOrder";
import { useProviderHealth, useFallbackOrder } from "@/hooks/useProviderHealth";
import type { FallbackChainEntry } from "@/hooks/useProviderHealth";

const CapabilityBadges = ({ capabilities }: { capabilities: ProviderWithCapabilities['capabilities'] }) => {
  const badges = [];
  if (capabilities.llm) badges.push(<Badge key="llm" variant="secondary" className="gap-1"><Brain className="w-3 h-3" />LLM</Badge>);
  if (capabilities.embedding) badges.push(<Badge key="embedding" variant="secondary" className="gap-1"><Database className="w-3 h-3" />Embed</Badge>);
  if (capabilities.audio_asr || capabilities.audio_tts) badges.push(<Badge key="audio" variant="secondary" className="gap-1"><Mic className="w-3 h-3" />Audio</Badge>);
  if (capabilities.vision) badges.push(<Badge key="vision" variant="secondary" className="gap-1"><EyeIcon className="w-3 h-3" />Vision</Badge>);
  return <div className="flex gap-1 flex-wrap">{badges}</div>;
};

interface ApiKeysSectionProps {
  apiKeys: ApiKey[];
  providers: ProviderInfo[];
  registryProviders: ProviderWithCapabilities[];
  providerApiKeys: ApiKeyInfo[];
  testingProvider: string | null;
  onSaveProviderApiKey: (provider: string, key: string) => Promise<void>;
  onDeleteProviderApiKey: (provider: string) => Promise<void>;
  onTestConnection: (provider: string) => void;
  onDeleteCustomProvider: (slug: string, displayName: string) => void;
}

export const ApiKeysSection = ({
  apiKeys, providers, registryProviders, providerApiKeys, testingProvider,
  onSaveProviderApiKey, onDeleteProviderApiKey, onTestConnection, onDeleteCustomProvider,
}: ApiKeysSectionProps) => {
  const [showNewKeyDialog, setShowNewKeyDialog] = useState(false);
  const [newKeyName, setNewKeyName] = useState("");
  const [newKeyValue, setNewKeyValue] = useState<string | null>(null);
  const [showKeyValue, setShowKeyValue] = useState(false);
  const [showApiKeyInput, setShowApiKeyInput] = useState<string | null>(null);
  const [newApiKey, setNewApiKey] = useState("");

  // Provider health + fallback order hooks
  const { healthData } = useProviderHealth();
  const { chain, enabled, saveFallbackOrder } = useFallbackOrder();

  // Build the provider list for the fallback order UI using the configured providers
  const fallbackProviders = (registryProviders.length > 0 ? registryProviders : providers)
    .filter((p: ProviderInfo | ProviderWithCapabilities) => ('requires_api_key' in p && p.requires_api_key) || ('is_custom' in p && p.is_custom))
    .map((provider: ProviderInfo | ProviderWithCapabilities) => {
      const storedKey = providerApiKeys.find((k) => k.provider === provider.name);
      // Prefer entries from the existing chain order; new providers go at the end
      return {
        id: `${provider.name}:${provider.llm_model ?? "default"}`,
        displayName: provider.display_name || provider.name,
        provider: provider.name,
        model: provider.llm_model ?? "default",
        hasKey: Boolean(storedKey),
      };
    });

  // Re-sort fallbackProviders to match the saved chain order
  const orderedProviders = chain.length > 0
    ? [
        ...chain
          .map((entry: FallbackChainEntry) =>
            fallbackProviders.find((p) => p.provider === entry.provider)
          )
          .filter(Boolean) as typeof fallbackProviders,
        ...fallbackProviders.filter(
          (p) => !chain.some((e: FallbackChainEntry) => e.provider === p.provider)
        ),
      ]
    : fallbackProviders;

  const handleOrderChange = (newChain: FallbackChainEntry[]) => {
    void saveFallbackOrder(newChain, enabled).then(() => {
      toast.success("Fallback order updated");
    });
  };

  const handleEnabledChange = (newEnabled: boolean) => {
    void saveFallbackOrder(
      chain,
      newEnabled,
    ).then(() => {
      toast.success(newEnabled ? "Fallback enabled" : "Fallback disabled");
    });
  };

  const handleCreateKey = () => {
    toast.info("API keys are not available yet");
    setShowNewKeyDialog(false);
    setNewKeyName("");
    setNewKeyValue(null);
  };

  const handleCopyKey = async (key: string) => {
    await navigator.clipboard.writeText(key);
    toast.success("API key copied to clipboard");
  };

  const handleSaveKey = async (provider: string) => {
    if (!newApiKey.trim()) return;
    await onSaveProviderApiKey(provider, newApiKey);
    setNewApiKey("");
    setShowApiKeyInput(null);
  };

  return (
    <div className="space-y-6">
      {/* Programmatic API Keys */}
      <SettingsCard title="Programmatic Access" description="API keys for external integrations">
        <div className="flex justify-end py-2">
          <Dialog open={showNewKeyDialog} onOpenChange={setShowNewKeyDialog}>
            <DialogTrigger asChild>
              <Button size="sm"><Plus className="w-4 h-4 mr-2" />Create Key</Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Create API Key</DialogTitle>
                <DialogDescription>{newKeyValue ? "Copy your new API key now. You won't be able to see it again." : "Enter a name for your new API key."}</DialogDescription>
              </DialogHeader>
              {newKeyValue ? (
                <div className="space-y-4">
                  <div className="flex items-center gap-2 p-3 rounded-lg bg-muted font-mono text-sm">
                    <span className="flex-1 truncate">{showKeyValue ? newKeyValue : "•".repeat(40)}</span>
                    <Button variant="ghost" size="icon" onClick={() => setShowKeyValue(!showKeyValue)}>{showKeyValue ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}</Button>
                    <Button variant="ghost" size="icon" onClick={() => handleCopyKey(newKeyValue)}><Copy className="w-4 h-4" /></Button>
                  </div>
                  <Button className="w-full" onClick={() => { setShowNewKeyDialog(false); setNewKeyValue(null); setNewKeyName(""); }}>Done</Button>
                </div>
              ) : (
                <>
                  <div className="space-y-2">
                    <Label htmlFor="key-name">Key Name</Label>
                    <Input id="key-name" value={newKeyName} onChange={(e) => setNewKeyName(e.target.value)} placeholder="e.g., Production API" />
                  </div>
                  <DialogFooter>
                    <Button variant="outline" onClick={() => setShowNewKeyDialog(false)}>Cancel</Button>
                    <Button onClick={handleCreateKey} disabled={!newKeyName.trim()}>Create</Button>
                  </DialogFooter>
                </>
              )}
            </DialogContent>
          </Dialog>
        </div>
        <div className="rounded-lg border border-border overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Key</TableHead>
                <TableHead>Created</TableHead>
                <TableHead>Last Used</TableHead>
                <TableHead className="w-[50px]"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {apiKeys.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-muted-foreground py-8">No API keys created yet.</TableCell>
                </TableRow>
              ) : (
                apiKeys.map((key) => (
                  <TableRow key={key.id}>
                    <TableCell className="font-medium">{key.name}</TableCell>
                    <TableCell className="font-mono text-muted-foreground">{key.prefix}•••••••••</TableCell>
                    <TableCell className="text-muted-foreground">{new Date(key.created_at).toLocaleDateString()}</TableCell>
                    <TableCell className="text-muted-foreground">{key.last_used ? new Date(key.last_used).toLocaleDateString() : "Never"}</TableCell>
                    <TableCell><Button variant="ghost" size="icon" className="text-destructive h-8 w-8"><Trash2 className="w-4 h-4" /></Button></TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </SettingsCard>

      {/* Provider API Keys */}
      <SettingsCard title="Provider API Keys" description="Keys are stored securely and never exposed">
        {(registryProviders.length > 0 ? registryProviders : providers)
          .filter((p: ProviderInfo | ProviderWithCapabilities) => ('requires_api_key' in p && p.requires_api_key) || ('is_custom' in p && p.is_custom))
          .map((provider: ProviderInfo | ProviderWithCapabilities) => {
            const storedKey = providerApiKeys.find((k) => k.provider === provider.name);
            const isInputOpen = showApiKeyInput === provider.name;
            const registryProvider = registryProviders.find((rp) => rp.name === provider.name);
            const isCustom = provider.is_custom;

            return (
              <div key={provider.name} className="flex items-start justify-between py-3 gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span className="font-medium text-sm">{provider.display_name}</span>
                    {isCustom && <Badge variant="secondary" className="text-xs">Custom</Badge>}
                    {registryProvider && <CapabilityBadges capabilities={registryProvider.capabilities} />}
                    {isCustom && (
                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-6 w-6 text-destructive"><Trash2 className="w-3 h-3" /></Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader><AlertDialogTitle>Delete Custom Provider?</AlertDialogTitle><AlertDialogDescription>This will remove "{provider.display_name}" and any stored API keys.</AlertDialogDescription></AlertDialogHeader>
                          <AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction onClick={() => onDeleteCustomProvider(provider.name, provider.display_name)} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">Delete Provider</AlertDialogAction></AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    )}
                  </div>
                  {storedKey ? <span className="text-xs text-muted-foreground font-mono">{storedKey.key_prefix}</span> : <span className="text-xs text-muted-foreground">No key configured</span>}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {storedKey && (
                    <>
                      <Button variant="outline" size="sm" onClick={() => onTestConnection(provider.name)} disabled={testingProvider === provider.name}>
                        {testingProvider === provider.name ? <Loader2 className="w-4 h-4 animate-spin" /> : "Test"}
                      </Button>
                      <AlertDialog>
                        <AlertDialogTrigger asChild><Button variant="ghost" size="icon" className="text-destructive"><Trash2 className="w-4 h-4" /></Button></AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader><AlertDialogTitle>Delete API Key?</AlertDialogTitle><AlertDialogDescription>This will remove the API key for {provider.display_name}.</AlertDialogDescription></AlertDialogHeader>
                          <AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction onClick={() => onDeleteProviderApiKey(provider.name)} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">Delete</AlertDialogAction></AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    </>
                  )}
                  {isInputOpen ? (
                    <div className="flex items-center gap-2">
                      <Input type="password" placeholder="Enter API key" value={newApiKey} onChange={(e) => setNewApiKey(e.target.value)} className="w-48" />
                      <Button size="sm" onClick={() => handleSaveKey(provider.name)} disabled={!newApiKey.trim()}>Save</Button>
                      <Button variant="outline" size="sm" onClick={() => { setShowApiKeyInput(null); setNewApiKey(""); }}>Cancel</Button>
                    </div>
                  ) : (
                    <Button variant="outline" size="sm" onClick={() => setShowApiKeyInput(provider.name)}>{storedKey ? "Update" : "Add Key"}</Button>
                  )}
                </div>
              </div>
            );
          })}
      </SettingsCard>

      {/* Provider Fallback Order */}
      {fallbackProviders.length > 0 && (
        <SettingsCard
          title="Provider Fallback Order"
          description="Configure automatic failover when a provider is unavailable"
        >
          <ProviderFallbackOrder
            providers={orderedProviders}
            healthData={healthData}
            enabled={enabled}
            onOrderChange={handleOrderChange}
            onEnabledChange={handleEnabledChange}
          />
        </SettingsCard>
      )}
    </div>
  );
};
