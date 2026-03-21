// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// OnboardingGuard -- route guard that intercepts unconfigured state
// Wraps WorkspaceLayout: shows OnboardingWizard until setup is complete,
// then passes through to children.

import { ReactNode, useCallback } from "react";
import { useSetupStatus } from "@/hooks/useSetupStatus";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import OnboardingWizard from "./OnboardingWizard";

interface OnboardingGuardProps {
  children: ReactNode;
}

const OnboardingGuard = ({ children }: OnboardingGuardProps) => {
  const { data, isLoading, error } = useSetupStatus();
  const queryClient = useQueryClient();

  const handleWizardComplete = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["setup-status"] });
  }, [queryClient]);

  // Show loading spinner while checking setup status
  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  // On error, pass through to workspace (fail-open for the guard -- setup
  // endpoint might not be available on older backends)
  if (error || !data) {
    return <>{children}</>;
  }

  // If not configured, show the onboarding wizard
  if (!data.configured) {
    return <OnboardingWizard onComplete={handleWizardComplete} />;
  }

  // Configured -- pass through to workspace
  return <>{children}</>;
};

export default OnboardingGuard;
