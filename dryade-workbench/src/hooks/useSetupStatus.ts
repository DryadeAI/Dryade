// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// React Query hook for checking onboarding setup status
// Calls GET /api/setup/status to determine if the instance is configured

import { useQuery } from "@tanstack/react-query";
import { fetchWithAuth } from "@/services/apiClient";

export interface SetupSteps {
  llm_provider: boolean;
  api_key: boolean;
  key_validated: boolean;
  mcp_configured: boolean;
  preferences_set: boolean;
}

export interface SetupStatus {
  configured: boolean;
  has_llm_provider: boolean;
  has_api_key: boolean;
  steps: SetupSteps;
}

export const useSetupStatus = () => {
  return useQuery<SetupStatus>({
    queryKey: ["setup-status"],
    queryFn: () =>
      fetchWithAuth<SetupStatus>("/setup/status", { requiresAuth: false }),
    staleTime: 30_000,
    retry: 1,
  });
};
