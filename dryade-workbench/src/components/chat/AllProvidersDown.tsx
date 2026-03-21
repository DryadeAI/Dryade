// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// AllProvidersDown — inline chat area component shown when all LLM providers fail.
// Renders a countdown timer with Retry Now / Cancel actions.

import { useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";

export interface AllProvidersDownProps {
  onRetry: () => void;
  onCancel: () => void;
}

const COUNTDOWN_START = 60;

/**
 * Inline degradation message shown when all LLM providers are unavailable.
 *
 * Displays a 60-second countdown. When the countdown reaches zero, onRetry
 * is called automatically. The user can also click "Retry Now" or "Cancel"
 * at any time.
 */
export function AllProvidersDown({ onRetry, onCancel }: AllProvidersDownProps) {
  const [countdown, setCountdown] = useState(COUNTDOWN_START);

  useEffect(() => {
    if (countdown <= 0) {
      onRetry();
      return;
    }

    const id = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          clearInterval(id);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(id);
  }, [countdown, onRetry]);

  return (
    <div className="flex flex-col items-center gap-4 p-6 rounded-lg border border-border bg-muted/50 text-center mx-4 my-2">
      <AlertTriangle className="w-8 h-8 text-yellow-500" aria-hidden="true" />

      <div className="space-y-1">
        <p className="text-sm font-semibold">All providers unavailable</p>
        <p className="text-xs text-muted-foreground">
          We're checking provider health. Auto-retrying in{" "}
          <span className="font-mono font-semibold">{countdown}s</span>
          ...
        </p>
      </div>

      <div className="flex gap-2">
        <Button size="sm" onClick={onRetry}>
          Retry Now
        </Button>
        <Button size="sm" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
