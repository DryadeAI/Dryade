// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// Loop Engine React Query hooks

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { loopsApi } from "@/services/api";
import type { LoopCreate, LoopUpdate } from "@/services/api/loops";

// ============== QUERY HOOKS ==============

export const useLoops = (filters?: { target_type?: string; enabled?: boolean }) => {
  return useQuery({
    queryKey: ["loops", filters],
    queryFn: () => loopsApi.list(filters),
  });
};

export const useLoop = (id: string) => {
  return useQuery({
    queryKey: ["loops", id],
    queryFn: () => loopsApi.get(id),
    enabled: !!id,
  });
};

export const useLoopExecutions = (
  loopId: string,
  params?: { status?: string; limit?: number; offset?: number }
) => {
  return useQuery({
    queryKey: ["loops", loopId, "executions", params],
    queryFn: () => loopsApi.getExecutions(loopId, params),
    enabled: !!loopId,
  });
};

// ============== MUTATION HOOKS ==============

export const useCreateLoop = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: LoopCreate) => loopsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["loops"] });
    },
  });
};

export const useUpdateLoop = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: LoopUpdate }) =>
      loopsApi.update(id, data),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: ["loops", id] });
      queryClient.invalidateQueries({ queryKey: ["loops"] });
    },
  });
};

export const useDeleteLoop = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => loopsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["loops"] });
    },
  });
};

export const useTriggerLoop = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => loopsApi.trigger(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: ["loops", id, "executions"] });
      queryClient.invalidateQueries({ queryKey: ["loops"] });
    },
  });
};

export const usePauseLoop = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => loopsApi.pause(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: ["loops", id] });
      queryClient.invalidateQueries({ queryKey: ["loops"] });
    },
  });
};

export const useResumeLoop = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => loopsApi.resume(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: ["loops", id] });
      queryClient.invalidateQueries({ queryKey: ["loops"] });
    },
  });
};
