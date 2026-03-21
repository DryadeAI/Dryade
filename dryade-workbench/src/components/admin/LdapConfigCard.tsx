// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Loader2, Check, X, Search } from "lucide-react";
import { toast } from "sonner";
import { adminApi } from "@/services/api/admin";
import type { LdapConfig, LdapSyncConfig, LdapGroupMapping, LdapSearchResult, LdapUser } from "@/types/admin";

export default function LdapConfigCard() {
  const { t } = useTranslation("admin");
  const queryClient = useQueryClient();

  const { data: status, isLoading: statusLoading, error: statusError } = useQuery({
    queryKey: ["admin", "ldap-status"],
    queryFn: () => adminApi.ldapGetStatus(),
    retry: false,
  });

  const ldapUnavailable = statusError && (statusError as Error & { status?: number })?.status === 503;

  const [config, setConfig] = useState<Partial<LdapConfig>>({
    server_url: "",
    bind_dn: "",
    bind_password: "",
    base_dn: "",
    use_tls: true,
    user_search_filter: "(objectClass=person)",
    connection_timeout: 10,
  });
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [syncOpen, setSyncOpen] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<LdapSearchResult | null>(null);
  const [searching, setSearching] = useState(false);
  const [syncConfig, setSyncConfig] = useState<LdapSyncConfig>({
    group_mappings: [],
    auto_create_users: true,
    auto_deactivate_missing: false,
  });

  // Load existing config
  const { data: existingConfig } = useQuery({
    queryKey: ["admin", "ldap-config"],
    queryFn: () => adminApi.ldapGetConfig(),
    enabled: !ldapUnavailable,
    retry: false,
  });

  useEffect(() => {
    if (existingConfig && 'server_url' in existingConfig) {
      setConfig({ ...existingConfig, bind_password: "" });
    }
  }, [existingConfig]);

  if (ldapUnavailable) {
    return (
      <Card>
        <CardContent className="py-6 text-center text-muted-foreground">
          {t("ldap.pluginUnavailable")}
        </CardContent>
      </Card>
    );
  }

  const handleSave = async () => {
    setSaving(true);
    try {
      await adminApi.ldapUpdateConfig(config as LdapConfig);
      toast.success(t("ldap.configSaved"));
      queryClient.invalidateQueries({ queryKey: ["admin", "ldap-status"] });
    } catch {
      toast.error(t("common.error"));
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    try {
      const result = await adminApi.ldapTestConnection();
      if (result.success) {
        toast.success(t("ldap.testSuccess"));
      } else {
        toast.error(`${t("ldap.testFailed")}: ${result.message}`);
      }
    } catch {
      toast.error(t("ldap.testFailed"));
    } finally {
      setTesting(false);
    }
  };

  const handleSearch = async () => {
    setSearching(true);
    try {
      const result = await adminApi.ldapSearchUsers(searchQuery || undefined, 50);
      setSearchResults(result);
    } catch {
      toast.error(t("common.error"));
    } finally {
      setSearching(false);
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    try {
      const result = await adminApi.ldapSync(syncConfig);
      toast.success(
        t("ldap.syncSuccess", {
          created: result.created,
          updated: result.updated,
          deactivated: result.deactivated,
        })
      );
      setSyncOpen(false);
      queryClient.invalidateQueries({ queryKey: ["admin", "ldap-status"] });
    } catch {
      toast.error(t("ldap.syncError"));
    } finally {
      setSyncing(false);
    }
  };

  return (
    <>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base">{t("directory.ldapTitle")}</CardTitle>
              <CardDescription className="text-xs">{t("directory.ldapDescription")}</CardDescription>
            </div>
            <div className="flex items-center gap-2">
              {statusLoading ? (
                <Skeleton className="h-5 w-20" />
              ) : (
                <>
                  <Badge variant={status?.configured ? "default" : "secondary"}>
                    {status?.configured ? t("ldap.configured") : t("ldap.notConfigured")}
                  </Badge>
                  {status?.last_sync && (
                    <span className="text-xs text-muted-foreground">
                      {t("ldap.lastSync")}: {new Date(status.last_sync).toLocaleString()}
                    </span>
                  )}
                </>
              )}
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-1">
              <label className="text-xs font-medium">{t("ldap.serverUrl")}</label>
              <Input
                placeholder={t("ldap.serverUrlPlaceholder")}
                value={config.server_url || ""}
                onChange={(e) => setConfig({ ...config, server_url: e.target.value })}
                className="h-9 text-sm"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium">{t("ldap.baseDn")}</label>
              <Input
                value={config.base_dn || ""}
                onChange={(e) => setConfig({ ...config, base_dn: e.target.value })}
                className="h-9 text-sm"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium">{t("ldap.bindDn")}</label>
              <Input
                value={config.bind_dn || ""}
                onChange={(e) => setConfig({ ...config, bind_dn: e.target.value })}
                className="h-9 text-sm"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium">{t("ldap.bindPassword")}</label>
              <Input
                type="password"
                placeholder="***"
                value={config.bind_password || ""}
                onChange={(e) => setConfig({ ...config, bind_password: e.target.value })}
                className="h-9 text-sm"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium">{t("ldap.userSearchFilter")}</label>
              <Input
                value={config.user_search_filter || ""}
                onChange={(e) => setConfig({ ...config, user_search_filter: e.target.value })}
                className="h-9 text-sm"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium">{t("ldap.connectionTimeout")}</label>
              <Input
                type="number"
                value={config.connection_timeout || 10}
                onChange={(e) => setConfig({ ...config, connection_timeout: parseInt(e.target.value, 10) })}
                className="h-9 text-sm w-24"
              />
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Switch
              checked={config.use_tls ?? true}
              onCheckedChange={(v) => setConfig({ ...config, use_tls: v })}
            />
            <label className="text-sm">{t("ldap.useTls")}</label>
          </div>

          <div className="flex gap-2">
            <Button onClick={handleSave} disabled={saving} size="sm">
              {saving && <Loader2 className="h-3 w-3 animate-spin mr-1" />}
              {t("ldap.saveConfig")}
            </Button>
            <Button variant="outline" onClick={handleTest} disabled={testing} size="sm">
              {testing && <Loader2 className="h-3 w-3 animate-spin mr-1" />}
              {t("ldap.testConnection")}
            </Button>
            <Button variant="outline" onClick={() => setSyncOpen(true)} size="sm">
              {t("ldap.syncUsers")}
            </Button>
          </div>

          {/* User Search */}
          <div className="border-t pt-4 mt-4">
            <div className="flex gap-2">
              <Input
                placeholder={t("common.search")}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="h-9 text-sm flex-1"
              />
              <Button variant="outline" size="sm" onClick={handleSearch} disabled={searching}>
                {searching ? <Loader2 className="h-3 w-3 animate-spin" /> : <Search className="h-3 w-3" />}
              </Button>
            </div>
            {searchResults?.users?.length > 0 && (
              <div className="border rounded-md mt-2 max-h-48 overflow-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-xs">UID</TableHead>
                      <TableHead className="text-xs">Email</TableHead>
                      <TableHead className="text-xs">Name</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {searchResults.users.map((u: LdapUser, i: number) => (
                      <TableRow key={i}>
                        <TableCell className="text-xs">{u.uid}</TableCell>
                        <TableCell className="text-xs">{u.email || "-"}</TableCell>
                        <TableCell className="text-xs">{u.display_name || "-"}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Sync Dialog */}
      <Dialog open={syncOpen} onOpenChange={setSyncOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("ldap.syncDialog.title")}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="flex items-center gap-2">
              <Switch
                checked={syncConfig.auto_create_users}
                onCheckedChange={(v) => setSyncConfig({ ...syncConfig, auto_create_users: v })}
              />
              <label className="text-sm">{t("ldap.syncDialog.autoCreateUsers")}</label>
            </div>
            <div className="flex items-center gap-2">
              <Switch
                checked={syncConfig.auto_deactivate_missing}
                onCheckedChange={(v) => setSyncConfig({ ...syncConfig, auto_deactivate_missing: v })}
              />
              <label className="text-sm">{t("ldap.syncDialog.autoDeactivate")}</label>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setSyncOpen(false)}>
                {t("common.cancel")}
              </Button>
              <Button onClick={handleSync} disabled={syncing}>
                {syncing && <Loader2 className="h-3 w-3 animate-spin mr-1" />}
                {t("ldap.syncDialog.sync")}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
