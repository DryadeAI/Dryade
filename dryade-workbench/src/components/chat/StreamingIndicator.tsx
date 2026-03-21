// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import React from "react";
import { cn } from "@/lib/utils";
import { CheckCircle2 } from "lucide-react";

interface StreamingIndicatorProps {
  tokenCount?: number;
  estimatedCost?: number;
  cached?: boolean;
  className?: string;
}

const StreamingIndicator = React.memo(function StreamingIndicator({
  tokenCount,
  estimatedCost,
  cached = false,
  className,
}: StreamingIndicatorProps) {
  return (
    <div className={cn("flex items-center gap-3 text-xs text-muted-foreground", className)}>
      {/* Animated dots */}
      <div className="flex items-center gap-1">
        <span className="animate-pulse">●</span>
        <span className="animate-pulse delay-100">●</span>
        <span className="animate-pulse delay-200">●</span>
      </div>

      {/* Token count */}
      {tokenCount !== undefined && (
        <span className="font-mono">{tokenCount} tokens</span>
      )}

      {/* Cached indicator */}
      {cached && (
        <span className="flex items-center gap-1 text-success">
          <CheckCircle2 size={12} />
          Cached
        </span>
      )}

      {/* Estimated cost */}
      {estimatedCost !== undefined && (
        <span className="font-mono">${estimatedCost.toFixed(4)}</span>
      )}
    </div>
  );
});

export default StreamingIndicator;
