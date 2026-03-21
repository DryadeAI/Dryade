// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// Provider health polling and fallback order state management hooks.
// Polls GET /api/provider-health every 10s and manages the user's fallback chain.

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchWithAuth } from "@/services/apiClient";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type HealthStatus = "green" | "yellow" | "red";

export interface ProviderHealthEntry {
  status: HealthStatus;
  state: string;
  failure_count: number;
  last_failure_time: number | null;
}

export interface ProviderHealthData {
  providers: Record<string, ProviderHealthEntry>;
}

export interface FallbackChainEntry {
  provider: string;
  model: string;
}

export interface FallbackOrderData {
  chain: FallbackChainEntry[];
  enabled: boolean;
}

// ---------------------------------------------------------------------------
// useProviderHealth — polls GET /api/provider-health every 10 seconds
// ---------------------------------------------------------------------------

export function useProviderHealth() {
  const query = useQuery<ProviderHealthData>({
    queryKey: ["provider-health"],
    queryFn: async () => {
      const response = await fetchWithAuth("/api/provider-health", {
        requiresAuth: true,
      });
      return response as ProviderHealthData;
    },
    refetchInterval: 10_000,
    staleTime: 5_000,
    retry: 2,
  });

  return {
    healthData: query.data?.providers ?? {},
    isLoading: query.isLoading,
    error: query.error as Error | null,
    refetch: query.refetch,
  };
}

// ---------------------------------------------------------------------------
// useFallbackOrder — fetches and mutates the user's fallback provider chain
// ---------------------------------------------------------------------------

export function useFallbackOrder() {
  const queryClient = useQueryClient();

  const query = useQuery<FallbackOrderData>({
    queryKey: ["provider-fallback-order"],
    queryFn: async () => {
      const response = await fetchWithAuth("/api/user/provider-fallback-order", {
        requiresAuth: true,
      });
      return response as FallbackOrderData;
    },
    staleTime: 30_000,
    retry: 1,
  });

  const mutation = useMutation({
    mutationFn: async (data: FallbackOrderData) => {
      await fetchWithAuth("/api/user/provider-fallback-order", {
        method: "PUT",
        requiresAuth: true,
        body: JSON.stringify(data),
        headers: { "Content-Type": "application/json" },
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["provider-fallback-order"] });
    },
  });

  return {
    chain: query.data?.chain ?? [],
    enabled: query.data?.enabled ?? false,
    isLoading: query.isLoading,
    saveFallbackOrder: (newChain: FallbackChainEntry[], enabled: boolean) =>
      mutation.mutateAsync({ chain: newChain, enabled }),
    isSaving: mutation.isPending,
  };
}
