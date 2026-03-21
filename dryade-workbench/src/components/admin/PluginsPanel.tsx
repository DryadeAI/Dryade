// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { fetchWithAuth } from "@/services/apiClient";
import {
  ShieldCheck,
  ShieldAlert,
  KeyRound,
  Users,
  Blocks,
  Puzzle,
} from "lucide-react";

interface AllowlistStatus {
  exists: boolean;
  valid: boolean;
  tier: string | null;
  max_users: number;
  current_users: number;
  custom_plugin_slots: number;
  custom_plugins_loaded: number;
  tofu_key_pinned: boolean;
  signature_valid: boolean;
  last_updated: string | null;
  version: string | null;
  expires_at: string | null;
}

function getBarColor(current: number, max: number): string {
  if (max === 0) return "bg-blue-500";
  const pct = (current / max) * 100;
  if (pct >= 100) return "bg-red-500";
  if (pct >= 80) return "bg-yellow-500";
  return "bg-blue-500";
}

function getBarWidth(current: number, max: number): string {
  if (max === 0) return "0%";
  return `${Math.min(100, (current / max) * 100)}%`;
}

export default function PluginsPanel() {
  const { t } = useTranslation("admin");
  const [status, setStatus] = useState<AllowlistStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [communityMode, setCommunityMode] = useState(false);

  useEffect(() => {
    fetchWithAuth<AllowlistStatus>(
      "/plugins/admin_dashboard/allowlist/status"
    )
      .then((data) => {
        setStatus(data);
        setLoading(false);
      })
      .catch(() => {
        setCommunityMode(true);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-8 w-48 bg-muted animate-pulse rounded" />
        <div className="h-32 bg-muted animate-pulse rounded-lg" />
        <div className="h-24 bg-muted animate-pulse rounded-lg" />
      </div>
    );
  }

  if (communityMode) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center max-w-md space-y-4 p-8 rounded-lg border border-border bg-card">
          <Puzzle className="w-12 h-12 text-blue-500 mx-auto" />
          <h3 className="text-lg font-semibold">
            {t("plugins.communityTitle", "Community Mode")}
          </h3>
          <p className="text-muted-foreground">
            {t(
              "plugins.communityDescription",
              "Plugin management requires an active enterprise license. Your instance is running in community mode with core features only."
            )}
          </p>
          <p className="text-sm text-muted-foreground/70">
            {t(
              "plugins.communityHint",
              "No license file detected at ~/.dryade/allowed-plugins.json"
            )}
          </p>
        </div>
      </div>
    );
  }

  if (!status) return null;

  return (
    <div className="space-y-6">
      {/* Allowlist Status */}
      <div className="rounded-lg border border-border bg-card p-6">
        <div className="flex items-center gap-2 mb-4">
          {status.valid ? (
            <ShieldCheck className="w-5 h-5 text-green-500" />
          ) : (
            <ShieldAlert className="w-5 h-5 text-red-500" />
          )}
          <h3 className="text-base font-semibold">
            {t("plugins.allowlistStatus", "Allowlist Status")}
          </h3>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
          <div>
            <p className="text-muted-foreground text-xs mb-1">Tier</p>
            <span
              className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                status.tier === "enterprise"
                  ? "bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300"
                  : status.tier === "team"
                  ? "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300"
                  : "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300"
              }`}
            >
              {status.tier
                ? status.tier.charAt(0).toUpperCase() + status.tier.slice(1)
                : "Unknown"}
            </span>
          </div>
          <div>
            <p className="text-muted-foreground text-xs mb-1">Signature</p>
            <span
              className={
                status.signature_valid ? "text-green-500" : "text-red-500"
              }
            >
              {status.signature_valid ? "Valid" : "Invalid"}
            </span>
          </div>
          <div>
            <p className="text-muted-foreground text-xs mb-1">TOFU Key</p>
            <div className="flex items-center gap-1">
              <KeyRound
                className={`w-3.5 h-3.5 ${
                  status.tofu_key_pinned
                    ? "text-green-500"
                    : "text-yellow-500"
                }`}
              />
              <span>
                {status.tofu_key_pinned ? "Pinned" : "Not Pinned"}
              </span>
            </div>
          </div>
          <div>
            <p className="text-muted-foreground text-xs mb-1">Version</p>
            <span>{status.version ?? "N/A"}</span>
          </div>
          <div>
            <p className="text-muted-foreground text-xs mb-1">Last Updated</p>
            <span>
              {status.last_updated
                ? new Date(status.last_updated).toLocaleDateString()
                : "N/A"}
            </span>
          </div>
          <div>
            <p className="text-muted-foreground text-xs mb-1">Expires</p>
            <span>
              {status.expires_at
                ? new Date(status.expires_at).toLocaleDateString()
                : "N/A"}
            </span>
          </div>
        </div>
      </div>

      {/* Resource Usage */}
      <div className="rounded-lg border border-border bg-card p-6">
        <h3 className="text-base font-semibold mb-4">
          {t("plugins.resourceUsage", "Resource Usage")}
        </h3>

        <div className="space-y-4">
          {/* Users quota */}
          <div>
            <div className="flex justify-between items-center mb-1.5">
              <div className="flex items-center gap-2 text-sm">
                <Users className="w-4 h-4 text-muted-foreground" />
                <span className="font-medium">Users</span>
              </div>
              <span className="text-sm text-muted-foreground">
                {status.max_users === 0
                  ? "Unlimited"
                  : `${status.current_users} / ${status.max_users}`}
              </span>
            </div>
            {status.max_users > 0 && (
              <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2.5">
                <div
                  className={`h-2.5 rounded-full transition-all ${getBarColor(
                    status.current_users,
                    status.max_users
                  )}`}
                  style={{
                    width: getBarWidth(
                      status.current_users,
                      status.max_users
                    ),
                  }}
                />
              </div>
            )}
          </div>

          {/* Plugin Slots quota */}
          <div>
            <div className="flex justify-between items-center mb-1.5">
              <div className="flex items-center gap-2 text-sm">
                <Blocks className="w-4 h-4 text-muted-foreground" />
                <span className="font-medium">Plugin Slots</span>
              </div>
              <span className="text-sm text-muted-foreground">
                {status.custom_plugin_slots === 0
                  ? "Unlimited"
                  : `${status.custom_plugins_loaded} / ${status.custom_plugin_slots}`}
              </span>
            </div>
            {status.custom_plugin_slots > 0 && (
              <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2.5">
                <div
                  className={`h-2.5 rounded-full transition-all ${getBarColor(
                    status.custom_plugins_loaded,
                    status.custom_plugin_slots
                  )}`}
                  style={{
                    width: getBarWidth(
                      status.custom_plugins_loaded,
                      status.custom_plugin_slots
                    ),
                  }}
                />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
