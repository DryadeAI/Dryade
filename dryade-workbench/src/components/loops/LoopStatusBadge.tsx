// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { Loop } from "@/services/api/loops";

interface LoopStatusBadgeProps {
  loop: Loop;
  className?: string;
}

/**
 * Status badge showing enabled/disabled state, last run status,
 * and relative next run time for a scheduled loop.
 */
export default function LoopStatusBadge({ loop, className }: LoopStatusBadgeProps) {
  return (
    <div className={cn("flex items-center gap-2", className)}>
      {/* Enabled/Disabled indicator */}
      <Badge
        variant={loop.enabled ? "default" : "secondary"}
        className={cn(
          "text-xs",
          loop.enabled
            ? "bg-green-500/15 text-green-700 dark:text-green-400 border-green-500/30"
            : "bg-muted text-muted-foreground"
        )}
      >
        <span
          className={cn(
            "inline-block w-1.5 h-1.5 rounded-full mr-1.5",
            loop.enabled ? "bg-green-500" : "bg-muted-foreground"
          )}
        />
        {loop.enabled ? "Active" : "Paused"}
      </Badge>

      {/* Next run time (relative) */}
      {loop.enabled && loop.next_run_at && (
        <span className="text-xs text-muted-foreground">
          Next: {formatRelativeTime(loop.next_run_at)}
        </span>
      )}

      {/* Last run time */}
      {loop.last_run_at && (
        <span className="text-xs text-muted-foreground">
          Last: {formatRelativeTime(loop.last_run_at)}
        </span>
      )}
    </div>
  );
}

/** Format an ISO datetime as a relative time string (e.g. "in 5 min", "3h ago"). */
function formatRelativeTime(isoDate: string): string {
  const now = Date.now();
  const target = new Date(isoDate).getTime();
  const diffMs = target - now;
  const absDiff = Math.abs(diffMs);

  const seconds = Math.floor(absDiff / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  let label: string;
  if (days > 0) label = `${days}d`;
  else if (hours > 0) label = `${hours}h`;
  else if (minutes > 0) label = `${minutes}m`;
  else label = `${seconds}s`;

  return diffMs > 0 ? `in ${label}` : `${label} ago`;
}
