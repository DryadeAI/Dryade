// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
/**
 * Capability status badge showing agent's tool/skill access level.
 * Uses color coding: green (full), yellow (partial), red (limited).
 */
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
/** Capability status levels for agent tool/skill access. */
export type CapabilityStatus = 'full' | 'partial' | 'limited';

interface CapabilityBadgeProps {
  status: CapabilityStatus;
  details?: string;
  className?: string;
}

const statusConfig: Record<
  CapabilityStatus,
  { label: string; description: string; dotClass: string; variant: "default" | "secondary" | "destructive" }
> = {
  full: {
    label: "Full",
    description: "All capabilities available",
    dotClass: "bg-green-500",
    variant: "default",
  },
  partial: {
    label: "Partial",
    description: "Some tools unavailable",
    dotClass: "bg-yellow-500",
    variant: "secondary",
  },
  limited: {
    label: "Limited",
    description: "MCP unavailable, skills only",
    dotClass: "bg-red-500",
    variant: "destructive",
  },
};

export function CapabilityBadge({ status, details, className }: CapabilityBadgeProps) {
  const config = statusConfig[status];

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge
          variant={config.variant}
          className={cn("text-xs cursor-help", className)}
        >
          <span
            className={cn("w-2 h-2 rounded-full mr-1.5", config.dotClass)}
          />
          {config.label}
        </Badge>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-xs">
        <p className="font-medium">{config.description}</p>
        {details && (
          <p className="text-xs text-muted-foreground mt-1">{details}</p>
        )}
      </TooltipContent>
    </Tooltip>
  );
}

export type { CapabilityBadgeProps };
