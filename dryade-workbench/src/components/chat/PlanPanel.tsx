// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// PlanPanel - Plan result viewing and plan data parsing utilities
// Extracted from ChatPage to encapsulate plan management UI

import React from "react";
import { ExecutionResultModal } from "@/components/workflow/ExecutionResultModal";
import type { PlanCardData, PlanExecution } from "@/types/extended-api";

// ============== Plan Data Parsing ==============

/**
 * Parse plan data from WS "complete" event exports.
 * Extracts plan_data from the exports object and transforms it
 * into a PlanCardData shape suitable for PlanCard rendering.
 *
 * @returns PlanCardData if plan data is present, null otherwise
 */
export function parsePlanExports(
  exports: Record<string, unknown> | undefined
): PlanCardData | null {
  const planDataRaw = exports?.plan_data as Record<string, unknown> | undefined;
  if (!planDataRaw) return null;

  return {
    id: undefined,
    name: (planDataRaw.name as string) || "Untitled Plan",
    description: (planDataRaw.description as string) || null,
    confidence: (planDataRaw.confidence as number) || 0.8,
    nodes: (
      (planDataRaw.nodes as { id: string; agent?: string; task?: string }[]) ||
      []
    ).map((n) => ({
      id: n.id,
      agent: n.agent || n.id || "Task",
      task: n.task || "",
      position: undefined,
    })),
    edges: (
      (planDataRaw.edges as { source: string; target: string }[]) || []
    ).map((e) => ({
      from: e.source,
      to: e.target,
    })),
    status: (planDataRaw.status as PlanCardData["status"]) || "draft",
    ai_generated: true,
    created_at: new Date().toISOString(),
  };
}

// ============== Plan Result Modal ==============

interface PlanResultModalProps {
  /** Whether the modal is open */
  open: boolean;
  /** Callback to change open state */
  onOpenChange: (open: boolean) => void;
  /** The selected plan execution result (from useChatState) */
  selectedPlanResult: PlanExecution | null;
  /** Name of the selected plan */
  selectedPlanName: string;
}

/**
 * Map PlanExecution status to ExecutionResultModal status enum.
 */
function mapPlanStatus(
  status: string | undefined
): "success" | "error" | "idle" {
  if (status === "completed") return "success";
  if (status === "failed") return "error";
  return "idle";
}

/**
 * PlanResultModal - Wraps ExecutionResultModal with plan-specific data mapping.
 *
 * Takes a PlanExecution from useChatState and maps it to the shape
 * expected by ExecutionResultModal. This avoids the verbose inline
 * data transformation that was previously in ChatPage's JSX.
 */
export const PlanResultModal = React.memo(function PlanResultModal({
  open,
  onOpenChange,
  selectedPlanResult,
  selectedPlanName,
}: PlanResultModalProps) {
  const result = selectedPlanResult
    ? {
        execution_id: selectedPlanResult.id,
        status: selectedPlanResult.status,
        started_at: selectedPlanResult.started_at,
        completed_at: selectedPlanResult.completed_at,
        duration_ms: selectedPlanResult.duration_ms,
        node_results: selectedPlanResult.node_results.map((nr) => ({
          node_id: nr.node_id,
          status: nr.status,
          output: nr.output,
          duration_ms: nr.duration_ms,
          error: nr.error,
        })),
      }
    : null;

  return (
    <ExecutionResultModal
      open={open}
      onOpenChange={onOpenChange}
      result={result}
      workflowName={selectedPlanName}
      status={mapPlanStatus(selectedPlanResult?.status)}
    />
  );
});

export default PlanResultModal;
