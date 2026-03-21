// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";
import { Server, Database, Search, Network, ExternalLink } from "lucide-react";
import type { ComponentStatus } from "@/types/api";

interface SystemHealthCardProps {
  components: ComponentStatus[];
  uptime: string;
  version: string;
}

const iconMap: Record<string, typeof Server> = {
  Database: Database,
  Redis: Database,
  Qdrant: Search,
  Neo4j: Network,
};

const statusColors = {
  healthy: "bg-success",
  degraded: "bg-warning",
  unhealthy: "bg-destructive",
};

const formatUptime = (seconds: number): string => {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  
  const parts = [];
  if (days > 0) parts.push(`${days}d`);
  if (hours > 0) parts.push(`${hours}h`);
  if (minutes > 0) parts.push(`${minutes}m`);
  
  return parts.join(' ') || '0m';
};

const SystemHealthCard = ({ components, uptime, version }: SystemHealthCardProps) => {
  return (
    <div className="glass-card p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-foreground">System Health</h2>
        <Link
          to="/workspace/health"
          className="text-xs text-muted-foreground hover:text-primary flex items-center gap-1 transition-colors"
        >
          Details <ExternalLink size={10} />
        </Link>
      </div>

      {/* Dependency Status Row */}
      <div className="flex flex-wrap gap-3 mb-4">
        {components.map((component) => {
          const Icon = iconMap[component.name] || Server;
          return (
            <div
              key={component.name}
              className="flex items-center gap-1.5"
              title={component.message || `${component.name}: ${component.status}`}
            >
              <Icon size={14} className="text-muted-foreground" />
              <span className="text-xs text-muted-foreground">{component.name}:</span>
              <span
                className={cn(
                  "w-2 h-2 rounded-full",
                  statusColors[component.status]
                )}
                aria-label={component.status}
              />
            </div>
          );
        })}
      </div>

      {/* Uptime & Version */}
      <div className="flex items-center justify-between text-xs text-muted-foreground border-t border-border pt-3">
        <span>Uptime: {uptime}</span>
        <span className="font-mono">{version}</span>
      </div>
    </div>
  );
};

export { SystemHealthCard, formatUptime };
export default SystemHealthCard;
