// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
/**
 * Check For Updates Button
 *
 * Triggers PM to immediately poll the marketplace for allowlist updates.
 * Shows toast notifications for the result.
 *
 * Part of Phase 164.4: Marketplace-to-PM delivery pipeline.
 */

import { useState, useCallback } from "react";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { pluginsApi } from "@/services/api";

interface CheckForUpdatesButtonProps {
  /** Optional CSS class override */
  className?: string;
  /** Optional label override */
  label?: string;
}

/**
 * Button that triggers PM to check marketplace for plugin updates.
 *
 * Shows a loading spinner while checking, then a toast with the result:
 * - Success: "Checking for plugin updates..." (non-blocking, auto-dismiss)
 * - PM unavailable: "Plugin manager not available" (warning toast)
 * - Network error: "Cannot reach server" (warning toast)
 *
 * Users never see technical details (ports, certificates, allowlist files).
 */
export const CheckForUpdatesButton = ({
  className,
  label = "Check for updates",
}: CheckForUpdatesButtonProps) => {
  const [isChecking, setIsChecking] = useState(false);

  const handleCheckForUpdates = useCallback(async () => {
    if (isChecking) return;
    setIsChecking(true);

    try {
      await pluginsApi.checkForUpdates();
      toast.info("Checking for plugin updates...", {
        description: "Plugin manager is polling the marketplace.",
        duration: 5000,
      });
    } catch (err: unknown) {
      const status = (err as { status?: number })?.status;
      if (status === 503) {
        toast.warning("Plugin manager not available", {
          description: "Start the plugin manager in poll or serve mode to check for updates.",
          duration: 5000,
        });
      } else {
        toast.warning("Cannot reach server", {
          description: "Failed to trigger update check. Please try again.",
          duration: 5000,
        });
      }
    } finally {
      setIsChecking(false);
    }
  }, [isChecking]);

  return (
    <Button
      variant="outline"
      size="sm"
      className={className}
      disabled={isChecking}
      onClick={() => void handleCheckForUpdates()}
      aria-label={isChecking ? "Checking for plugin updates..." : label}
    >
      <RefreshCw
        className={`w-4 h-4 mr-2 ${isChecking ? "motion-safe:animate-spin" : ""}`}
        aria-hidden="true"
      />
      {isChecking ? "Checking..." : label}
    </Button>
  );
};

export default CheckForUpdatesButton;
