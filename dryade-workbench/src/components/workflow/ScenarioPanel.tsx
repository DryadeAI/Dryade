// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
/**
 * ScenarioPanel - Workflow/Scenario selector dropdown with status indicators.
 *
 * Extracted from WorkflowPage.tsx (Phase 117-07, Task 2).
 * Renders the left side of the workflow header: dropdown selector,
 * AI badge, status badge, result button, and stuck-plan banner.
 */
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
  DropdownMenuLabel,
  DropdownMenuGroup,
} from "@/components/ui/dropdown-menu";
import { FolderOpen, ChevronDown, Plus, Sparkles, FileCode, Bot } from "lucide-react";
import { cn } from "@/lib/utils";
import type { WorkflowStatus } from "@/components/workflow/WorkflowHeader";
import type { ScenarioInfo, Plan } from "@/types/extended-api";
import type { WorkflowListItem } from "@/services/api";

export interface ScenarioPanelProps {
  // Data
  workflows: ScenarioInfo[];
  userPlans: Plan[];
  myWorkflows: WorkflowListItem[];
  workflowsLoading: boolean;

  // Selection state
  selectedWorkflowId: string | null;
  selectedWorkflow: ScenarioInfo | null;
  selectedPlan: Plan | null;
  currentWorkflowId: number | null;
  isAIGenerated: boolean;

  // Execution state
  workflowStatus: WorkflowStatus;
  workflowResult: unknown;
  isRunning: boolean;
  backendPlanStatus: string | null;
  hasPlanId: boolean;

  // Actions
  onCreateWorkflow: () => void;
  onSelectWorkflow: (workflow: ScenarioInfo) => void;
  onSelectPlan: (plan: Plan) => void;
  onLoadWorkflowById: (id: number) => void;
  onViewResult: () => void;
  onResetStuckPlan: () => void;
}

export const ScenarioPanel = ({
  workflows,
  userPlans,
  myWorkflows,
  workflowsLoading,
  selectedWorkflowId,
  selectedWorkflow,
  selectedPlan,
  currentWorkflowId,
  isAIGenerated,
  workflowStatus,
  workflowResult,
  isRunning,
  backendPlanStatus,
  hasPlanId,
  onCreateWorkflow,
  onSelectWorkflow,
  onSelectPlan,
  onLoadWorkflowById,
  onViewResult,
  onResetStuckPlan,
}: ScenarioPanelProps) => {
  return (
    <div className="flex items-center gap-3">
      {/* Unified Workflow Selector Dropdown */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" className="gap-2 min-w-[200px] justify-between">
            <div className="flex items-center gap-2">
              {selectedPlan ? (
                <Sparkles size={14} className="text-purple-500" />
              ) : currentWorkflowId ? (
                <FolderOpen size={14} className="text-blue-500" />
              ) : (
                <FolderOpen size={14} className="text-primary" />
              )}
              <span className="truncate">
                {workflowsLoading ? (
                  <Skeleton className="h-4 w-24" />
                ) : selectedPlan ? (
                  selectedPlan.name
                ) : currentWorkflowId ? (
                  myWorkflows.find(w => w.id === currentWorkflowId)?.name || "Custom Workflow"
                ) : (
                  selectedWorkflow?.display_name || "Select workflow"
                )}
              </span>
            </div>
            <ChevronDown size={14} className="text-muted-foreground" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-[300px] max-h-[400px] overflow-y-auto">
          <DropdownMenuItem
            onClick={onCreateWorkflow}
            className="gap-2 text-primary"
          >
            <Plus size={14} />
            <span>New Workflow</span>
          </DropdownMenuItem>

          {/* Custom Workflows */}
          {myWorkflows.length > 0 && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuLabel className="flex items-center gap-2">
                <FolderOpen size={12} className="text-blue-500" />
                Custom Workflows
              </DropdownMenuLabel>
              <DropdownMenuGroup>
                {myWorkflows.map((w) => (
                  <DropdownMenuItem
                    key={`wf-${w.id}`}
                    onClick={() => onLoadWorkflowById(w.id)}
                    className={cn(
                      "flex items-center justify-between",
                      currentWorkflowId === w.id && "bg-blue-500/10"
                    )}
                  >
                    <div className="flex items-center gap-2 truncate">
                      <FolderOpen size={12} className="text-blue-500 shrink-0" />
                      <span className="truncate">{w.name}</span>
                    </div>
                    <Badge variant="outline" className="text-[10px] ml-2">
                      {w.status}
                    </Badge>
                  </DropdownMenuItem>
                ))}
              </DropdownMenuGroup>
            </>
          )}

          {/* AI Plans */}
          {userPlans.length > 0 && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuLabel className="flex items-center gap-2">
                <Sparkles size={12} className="text-purple-500" />
                AI Plans
              </DropdownMenuLabel>
              <DropdownMenuGroup>
                {userPlans.map((plan) => (
                  <DropdownMenuItem
                    key={`plan-${plan.id}`}
                    onClick={() => onSelectPlan(plan)}
                    className={cn(
                      "flex items-center justify-between",
                      selectedPlan?.id === plan.id && "bg-purple-500/10"
                    )}
                  >
                    <div className="flex items-center gap-2 truncate">
                      <Bot size={12} className="text-purple-500 shrink-0" />
                      <span className="truncate">{plan.name}</span>
                    </div>
                    <Badge variant="outline" className="text-[10px] ml-2 bg-purple-500/10 text-purple-500 border-purple-500/20">
                      AI
                    </Badge>
                  </DropdownMenuItem>
                ))}
              </DropdownMenuGroup>
            </>
          )}

          {/* System Templates */}
          {workflows.length > 0 && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuLabel className="flex items-center gap-2">
                <FileCode size={12} className="text-muted-foreground" />
                Templates
              </DropdownMenuLabel>
              <DropdownMenuGroup>
                {workflows.map((workflow) => (
                  <DropdownMenuItem
                    key={workflow.name}
                    onClick={() => onSelectWorkflow(workflow)}
                    className={cn(
                      "flex items-center justify-between",
                      selectedWorkflowId === workflow.name && !selectedPlan && "bg-primary/10"
                    )}
                  >
                    <span className="truncate">{workflow.display_name}</span>
                    <Badge variant="outline" className="text-[10px] ml-2">
                      {workflow.domain}
                    </Badge>
                  </DropdownMenuItem>
                ))}
              </DropdownMenuGroup>
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>

      {/* AI Generated badge */}
      {isAIGenerated && (
        <Badge variant="secondary" className="gap-1 text-xs bg-purple-500/10 text-purple-500 border-purple-500/20 shrink-0">
          <Sparkles size={12} />
          AI Generated
        </Badge>
      )}

      {/* Status badge + View Result */}
      {(selectedWorkflow || isAIGenerated) && (
        <>
          <Badge
            variant={
              workflowStatus === "running"
                ? "default"
                : workflowStatus === "success"
                ? "outline"
                : workflowStatus === "error"
                ? "destructive"
                : "secondary"
            }
            className="shrink-0"
          >
            {workflowStatus === "idle" ? "Ready" : workflowStatus}
          </Badge>
          {workflowResult && workflowStatus === "success" && (
            <Button
              variant="ghost"
              size="sm"
              className="gap-1 text-xs text-muted-foreground hover:text-foreground"
              onClick={onViewResult}
            >
              <span>View Result</span>
            </Button>
          )}
        </>
      )}

      {/* Reset stuck plan banner */}
      {backendPlanStatus === "executing" && !isRunning && hasPlanId && (
        <Badge
          variant="destructive"
          className="shrink-0 gap-1.5 cursor-pointer hover:bg-destructive/80 transition-colors"
          onClick={onResetStuckPlan}
        >
          Plan stuck - Click to reset
        </Badge>
      )}
    </div>
  );
};

export default ScenarioPanel;
