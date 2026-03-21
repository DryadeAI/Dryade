// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Sparkles, ExternalLink, Loader2, Eye, CheckCircle2, XCircle, RotateCcw, Play } from "lucide-react";
import { plansApi } from "@/services/api";
import { MiniGraph } from "@/components/shared/MiniGraph";
import type { PlanCardData } from "@/types/extended-api";
import { toast } from "sonner";

interface PlanCardProps {
  plan: PlanCardData;
  onPlanSaved?: (savedPlanId: number) => void;
  /** Conversation ID for saving unsaved plans - required when plan.id is undefined */
  conversationId?: string;
  /** Callback to view execution results for a completed/failed plan */
  onViewResults?: (planId: number) => void;
  /** Callback when plan status changes (approve, cancel, reset) */
  onStatusChange?: (planId: number, newStatus: PlanCardData["status"]) => void;
}

/** Status badge color mapping */
const statusStyles: Record<PlanCardData["status"], string> = {
  draft: "bg-muted text-muted-foreground",
  approved: "bg-primary/20 text-primary",
  executing: "bg-warning/20 text-warning",
  completed: "bg-success/20 text-success",
  failed: "bg-destructive/20 text-destructive",
  cancelled: "bg-muted text-muted-foreground",
};

/** Plan card component for inline chat display */
export default function PlanCard({ plan, onPlanSaved, conversationId, onViewResults, onStatusChange }: PlanCardProps) {
  const navigate = useNavigate();
  const [isSaving, setIsSaving] = useState(false);
  const [isActioning, setIsActioning] = useState(false);

  const handleEditInWorkflow = async () => {
    setIsSaving(true);
    try {
      let planId = plan.id;

      if (!planId) {
        // Plan has no ID - save it first via createPlan
        // Backend expects nodes/edges as top-level fields, not nested in plan_json
        const savedPlan = await plansApi.createPlan({
          name: plan.name,
          description: plan.description || "",
          conversation_id: conversationId || crypto.randomUUID(), // Use provided conversation or generate new
          nodes: plan.nodes.map((n) => ({
            id: n.id,
            agent: n.agent,
            task: n.task,
            depends_on: plan.edges
              .filter((e) => e.to === n.id)
              .map((e) => e.from),
          })),
          edges: plan.edges.map((e, idx) => ({
            id: `edge-${idx}`,
            from: e.from,
            to: e.to,
          })),
          confidence: plan.confidence,
          ai_generated: plan.ai_generated,
        });
        planId = savedPlan.id;
        onPlanSaved?.(planId);
        toast.success("Plan saved");
      } else {
        // Plan already has ID - update it
        // Backend expects nodes/edges as top-level fields, not nested in plan_json
        await plansApi.updatePlan(planId, {
          name: plan.name,
          description: plan.description || "",
          nodes: plan.nodes.map((n) => ({
            id: n.id,
            agent: n.agent,
            task: n.task,
            depends_on: plan.edges
              .filter((e) => e.to === n.id)
              .map((e) => e.from),
          })),
          edges: plan.edges.map((e, idx) => ({
            id: `edge-${idx}`,
            from: e.from,
            to: e.to,
          })),
        });
        toast.success("Plan updated");
      }

      // Navigate to workflow page with saved plan ID
      navigate(`/workspace/workflows?planId=${planId}`);
    } catch (error) {
      toast.error("Failed to save plan before opening editor");
      console.error(error);
    } finally {
      setIsSaving(false);
    }
  };

  const handleApprove = async () => {
    if (!plan.id) return;
    setIsActioning(true);
    try {
      await plansApi.approvePlan(plan.id);
      toast.success("Plan approved");
      onStatusChange?.(plan.id, "approved");
    } catch (error) {
      toast.error("Failed to approve plan");
      console.error(error);
    } finally {
      setIsActioning(false);
    }
  };

  const handleCancel = async () => {
    if (!plan.id) return;
    setIsActioning(true);
    try {
      await plansApi.cancelPlan(plan.id);
      toast.success("Plan cancelled");
      onStatusChange?.(plan.id, "cancelled");
    } catch (error) {
      toast.error("Failed to cancel plan");
      console.error(error);
    } finally {
      setIsActioning(false);
    }
  };

  const handleReset = async () => {
    if (!plan.id) return;
    setIsActioning(true);
    try {
      await plansApi.resetStuckPlan(plan.id);
      toast.success("Plan reset to failed - you can now retry or edit");
      onStatusChange?.(plan.id, "failed");
    } catch (error) {
      toast.error("Failed to reset plan");
      console.error(error);
    } finally {
      setIsActioning(false);
    }
  };

  const handleExecute = async () => {
    if (!plan.id) return;
    setIsActioning(true);
    try {
      await plansApi.executePlan(plan.id);
      toast.success("Plan execution started");
      onStatusChange?.(plan.id, "executing");
    } catch (error) {
      toast.error("Failed to execute plan");
      console.error(error);
    } finally {
      setIsActioning(false);
    }
  };

  const confidencePercent = Math.round(plan.confidence * 100);

  return (
    <Card variant="glass" className="w-full max-w-2xl">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-base font-medium flex items-center gap-2">
            {plan.name}
            {plan.ai_generated && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <Badge
                    variant="secondary"
                    className="gap-1 px-1.5 py-0.5 text-[10px]"
                  >
                    <Sparkles className="h-3 w-3" />
                    AI Generated
                  </Badge>
                </TooltipTrigger>
                <TooltipContent>
                  This plan was generated by AI based on your request
                </TooltipContent>
              </Tooltip>
            )}
          </CardTitle>
        </div>
        {plan.description && (
          <p className="text-sm text-muted-foreground line-clamp-2 mt-1">
            {plan.description}
          </p>
        )}
      </CardHeader>

      <CardContent className="space-y-3">
        {/* Mini workflow graph */}
        {plan.nodes.length > 0 && (
          <MiniGraph
            nodes={plan.nodes.map((n) => ({
              id: n.id,
              label: n.agent,
              sublabel: n.task,
            }))}
            edges={plan.edges}
            className="w-full h-[180px] bg-muted/30 rounded-md"
          />
        )}

        {/* Footer: badges and action buttons */}
        <div className="flex items-center justify-between pt-2 border-t border-border/50">
          <div className="flex items-center gap-2">
            <Tooltip>
              <TooltipTrigger asChild>
                <Badge
                  variant="outline"
                  className={cn(
                    "text-[10px] px-2 py-0.5",
                    confidencePercent >= 80
                      ? "border-success/50 text-success"
                      : confidencePercent >= 50
                        ? "border-warning/50 text-warning"
                        : "border-destructive/50 text-destructive"
                  )}
                >
                  {confidencePercent}% confidence
                </Badge>
              </TooltipTrigger>
              <TooltipContent>
                AI confidence in plan correctness
              </TooltipContent>
            </Tooltip>

            <Badge
              variant="outline"
              className={cn("text-[10px] px-2 py-0.5", statusStyles[plan.status])}
            >
              {plan.status}
            </Badge>
          </div>

          <div className="flex items-center gap-2">
            {/* Approve button - shown for draft plans with an ID */}
            {plan.id && plan.status === "draft" && (
              <Button
                size="sm"
                variant="outline"
                onClick={handleApprove}
                disabled={isActioning}
                className="gap-1.5 border-success/50 text-success hover:bg-success/10"
              >
                <CheckCircle2 className="h-3 w-3" />
                Approve
              </Button>
            )}

            {/* Execute button - shown for approved or draft plans (GAP-P8) */}
            {plan.id && ["draft", "approved"].includes(plan.status) && (
              <Button
                size="sm"
                variant="outline"
                onClick={handleExecute}
                disabled={isActioning}
                className="gap-1.5 border-primary/50 text-primary hover:bg-primary/10"
              >
                <Play className="h-3 w-3" />
                Execute
              </Button>
            )}

            {/* Cancel button - shown for executing or approved plans */}
            {plan.id && ["executing", "approved"].includes(plan.status) && (
              <Button
                size="sm"
                variant="outline"
                onClick={plan.status === "executing" ? handleReset : handleCancel}
                disabled={isActioning}
                className="gap-1.5 border-destructive/50 text-destructive hover:bg-destructive/10"
              >
                {plan.status === "executing" ? (
                  <>
                    <RotateCcw className="h-3 w-3" />
                    Reset
                  </>
                ) : (
                  <>
                    <XCircle className="h-3 w-3" />
                    Cancel
                  </>
                )}
              </Button>
            )}

            {/* View Results button - shown for executed plans */}
            {plan.id && onViewResults && ["completed", "failed", "cancelled"].includes(plan.status) && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => onViewResults(plan.id!)}
                className="gap-1.5"
              >
                <Eye className="h-3 w-3" />
                View Results
              </Button>
            )}

            {/* Edit in Workflow - not shown for executing plans */}
            {plan.status !== "executing" && (
              <Button
                size="sm"
                variant="default"
                onClick={handleEditInWorkflow}
                disabled={isSaving}
                className="gap-1.5"
              >
                {isSaving ? (
                  <>
                    <Loader2 className="h-3 w-3 animate-spin" />
                    Saving...
                  </>
                ) : (
                  <>
                    <ExternalLink className="h-3 w-3" />
                    Edit in Workflow
                  </>
                )}
              </Button>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
