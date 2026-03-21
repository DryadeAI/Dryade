// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { Package, Puzzle } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export interface InstalledPlugin {
  name: string;
  version: string | null;
  /** "encrypted" for .dryadepkg marketplace plugins, "custom" for directory plugins */
  type: "encrypted" | "custom" | string;
  /** "loaded" = active, "inactive" = on disk but not loaded, "error" = load error */
  status: "loaded" | "inactive" | "error" | string;
}

interface InstalledPluginCardProps {
  plugin: InstalledPlugin;
}

function toDisplayName(name: string): string {
  return name
    .replace(/[_-]+/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

const statusDot: Record<string, string> = {
  loaded: "bg-success",
  inactive: "bg-muted-foreground/60",
  error: "bg-destructive",
};

const statusLabel: Record<string, string> = {
  loaded: "Active",
  inactive: "Inactive",
  error: "Error",
};

const typeBadgeClass: Record<string, string> = {
  encrypted:
    "bg-purple-500/10 text-purple-600 border-purple-500/30",
  custom:
    "bg-blue-500/10 text-blue-600 border-blue-500/30",
};

/**
 * Compact card displaying an installed plugin's name, version, type
 * (marketplace/encrypted or custom directory), and load status indicator.
 */
export function InstalledPluginCard({ plugin }: InstalledPluginCardProps) {
  const displayName = toDisplayName(plugin.name);
  const dotClass = statusDot[plugin.status] ?? "bg-muted-foreground/40";
  const labelText = statusLabel[plugin.status] ?? plugin.status;
  const typeLabel = plugin.type === "encrypted" ? "Marketplace" : "Custom";
  const badgeClass =
    typeBadgeClass[plugin.type] ??
    "bg-muted/10 text-muted-foreground border-border/30";

  return (
    <Card className="bg-card/60 backdrop-blur-md hover:border-primary/40 transition-colors duration-150">
      <CardContent className="p-4">
        <div className="flex items-center gap-3">
          {/* Icon */}
          <div className="flex-shrink-0 flex items-center justify-center w-10 h-10 rounded-lg bg-primary/10">
            {plugin.type === "encrypted" ? (
              <Package className="w-5 h-5 text-primary" aria-hidden="true" />
            ) : (
              <Puzzle className="w-5 h-5 text-primary" aria-hidden="true" />
            )}
          </div>

          {/* Name + version */}
          <div className="flex-1 min-w-0">
            <p className="font-medium text-sm truncate" title={displayName}>
              {displayName}
            </p>
            {plugin.version && (
              <p className="text-xs text-muted-foreground">
                v{plugin.version}
              </p>
            )}
          </div>

          {/* Type + status */}
          <div className="flex flex-col items-end gap-1.5 flex-shrink-0">
            <Badge variant="outline" className={cn("text-xs", badgeClass)}>
              {typeLabel}
            </Badge>
            <div className="flex items-center gap-1.5">
              <span
                className={cn("w-2 h-2 rounded-full", dotClass)}
                aria-hidden="true"
              />
              <span className="text-xs text-muted-foreground">{labelText}</span>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
