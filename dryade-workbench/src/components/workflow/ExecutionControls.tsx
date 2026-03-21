// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
/**
 * ExecutionControls - Workflow action toolbar (right side of header).
 *
 * Extracted from WorkflowPage.tsx (Phase 117-07, Task 2).
 * Renders: undo/redo, plan delete, custom workflow actions (publish/archive/delete/share),
 * keyboard shortcuts tooltip, plugin toolbar slot, and WorkflowHeader run/save controls.
 */
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Keyboard, Undo2, Redo2, Trash2, Archive, Globe, Share2 } from "lucide-react";
import WorkflowHeader from "@/components/workflow/WorkflowHeader";
import type { WorkflowStatus } from "@/components/workflow/WorkflowHeader";
import { PluginSlot } from "@/plugins/slots";
import { shortcuts } from "@/hooks/useWorkflowState";
import type { Plan } from "@/types/extended-api";

export interface ExecutionControlsProps {
  // Undo/Redo
  canUndo: boolean;
  canRedo: boolean;
  onUndo: () => void;
  onRedo: () => void;

  // Plan deletion
  selectedPlan: Plan | null;
  isRunning: boolean;
  onDeleteDialogOpen: () => void;

  // Custom workflow actions (GAP-W8)
  currentWorkflowId: number | null;
  publishPending: boolean;
  archivePending: boolean;
  deletePending: boolean;
  onPublish: () => void;
  onArchive: () => void;
  onDeleteCustomWorkflow: (id: number) => void;

  // Share (GAP-W9)
  onOpenShare: () => void;

  // Plugin slot
  selectedWorkflowName?: string;

  // WorkflowHeader props
  workflowStatus: WorkflowStatus;
  currentStep?: number;
  totalSteps?: number;
  validateOnRun: boolean;
  onValidateOnRunChange: (value: boolean) => void;
  onReset: () => void;
  onSave: () => void;
  onSaveAsTemplate: () => void;
  onRun: () => void;
  onStop: () => void;
  isAIGenerated: boolean;
}

export const ExecutionControls = ({
  canUndo,
  canRedo,
  onUndo,
  onRedo,
  selectedPlan,
  isRunning,
  onDeleteDialogOpen,
  currentWorkflowId,
  publishPending,
  archivePending,
  deletePending,
  onPublish,
  onArchive,
  onDeleteCustomWorkflow,
  onOpenShare,
  selectedWorkflowName,
  workflowStatus,
  currentStep,
  totalSteps,
  validateOnRun,
  onValidateOnRunChange,
  onReset,
  onSave,
  onSaveAsTemplate,
  onRun,
  onStop,
  isAIGenerated,
}: ExecutionControlsProps) => {
  return (
    <div className="flex items-center gap-2">
      {/* Undo/Redo Buttons */}
      <div className="flex items-center border border-border rounded-lg">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 rounded-r-none"
              onClick={onUndo}
              disabled={!canUndo}
            >
              <Undo2 size={14} />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Undo (Cmd+Z)</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 rounded-l-none border-l border-border"
              onClick={onRedo}
              disabled={!canRedo}
            >
              <Redo2 size={14} />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Redo (Cmd+Shift+Z)</TooltipContent>
        </Tooltip>
      </div>

      {/* Delete Plan Button */}
      {selectedPlan && (
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-muted-foreground hover:text-destructive hover:bg-destructive/10"
              onClick={onDeleteDialogOpen}
              disabled={isRunning}
            >
              <Trash2 size={14} />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Delete Plan</TooltipContent>
        </Tooltip>
      )}

      {/* Custom workflow actions */}
      {currentWorkflowId && (
        <>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-muted-foreground hover:text-green-600"
                onClick={onPublish}
                disabled={publishPending}
              >
                <Globe size={14} />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Publish Workflow</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-muted-foreground hover:text-yellow-600"
                onClick={onArchive}
                disabled={archivePending}
              >
                <Archive size={14} />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Archive Workflow</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                onClick={() => onDeleteCustomWorkflow(currentWorkflowId)}
                disabled={deletePending}
              >
                <Trash2 size={14} />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Delete Workflow</TooltipContent>
          </Tooltip>
        </>
      )}

      {/* Share button */}
      {currentWorkflowId && (
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-muted-foreground hover:text-primary"
              onClick={onOpenShare}
            >
              <Share2 size={14} />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Share Workflow</TooltipContent>
        </Tooltip>
      )}

      {/* Keyboard Shortcuts Button */}
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
          >
            <Keyboard size={16} />
          </Button>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="max-w-xs">
          <div className="space-y-1">
            {shortcuts.map((s, i) => (
              <div key={i} className="flex items-center justify-between gap-4 text-xs">
                <span className="text-muted-foreground">{s.action}</span>
                <div className="flex gap-0.5">
                  {s.keys.map((k) => (
                    <kbd
                      key={k}
                      className="px-1.5 py-0.5 bg-muted rounded text-[10px] font-mono"
                    >
                      {k}
                    </kbd>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </TooltipContent>
      </Tooltip>

      {/* Plugin toolbar extensions */}
      <PluginSlot
        name="workflow-toolbar"
        hostData={{ workflowId: selectedWorkflowName }}
        className="flex items-center gap-2"
      />

      {/* Workflow Controls */}
      <WorkflowHeader
        isRunning={isRunning}
        workflowStatus={workflowStatus}
        currentStep={isRunning ? currentStep : undefined}
        totalSteps={isRunning ? totalSteps : undefined}
        validateOnRun={validateOnRun}
        onValidateOnRunChange={onValidateOnRunChange}
        onReset={onReset}
        onSave={onSave}
        onSaveAsTemplate={onSaveAsTemplate}
        onRun={onRun}
        onStop={onStop}
        compact
        aiGenerated={isAIGenerated}
      />
    </div>
  );
};

export default ExecutionControls;
