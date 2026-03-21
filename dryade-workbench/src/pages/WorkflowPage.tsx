// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
/**
 * WorkflowPage - Composition layer for the workflow editor.
 *
 * Decomposed in Phase 117-07:
 * - State management: useWorkflowState hook
 * - Scenario selector: ScenarioPanel component
 * - Toolbar actions: ExecutionControls component
 * - Node inspection: NodeInspector (standalone, used by UnifiedContextPanel)
 * - This file: layout composition + dialogs
 *
 * Phase 173-03: Replaced SidebarPanel with UnifiedContextPanel (4-tab unified panel).
 * Scenarios and Run History are now tabs in the right panel.
 * Execution log bottom panel is always accessible via toggle button.
 */
import WorkflowCanvas from "@/components/workflow/WorkflowCanvas";
import UnifiedContextPanel from "@/components/workflow/UnifiedContextPanel";
import { ScenarioPanel } from "@/components/workflow/ScenarioPanel";
import { ExecutionControls } from "@/components/workflow/ExecutionControls";
import { WorkflowInputModal } from "@/components/workflow/WorkflowInputModal";
import { ExecutionResultModal } from "@/components/workflow/ExecutionResultModal";
import { ExecutionLog } from "@/components/workflow/ExecutionLog";
import { CollapsiblePanel } from "@/components/layout/panels";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Loader2, Share2, UserX, ChevronUp, ChevronDown, Terminal } from "lucide-react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { PluginSlot } from "@/plugins/slots";
import { useWorkflowState } from "@/hooks/useWorkflowState";
import type { WorkflowNode } from "@/types/workflow";
import { useTranslation } from 'react-i18next';

const WorkflowPage = () => {
  const { t } = useTranslation('workflows');
  const wf = useWorkflowState();

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Header */}
      <header className="px-4 py-3 border-b border-border flex items-center justify-between bg-card/50 shrink-0">
        <ScenarioPanel
          workflows={wf.workflows}
          userPlans={wf.userPlans}
          myWorkflows={wf.myWorkflows}
          workflowsLoading={wf.workflowsLoading}
          selectedWorkflowId={wf.selectedWorkflowId}
          selectedWorkflow={wf.selectedWorkflow}
          selectedPlan={wf.selectedPlan}
          currentWorkflowId={wf.currentWorkflowId}
          isAIGenerated={wf.isAIGenerated}
          workflowStatus={wf.workflowStatus}
          workflowResult={wf.workflowResult}
          isRunning={wf.isRunning}
          backendPlanStatus={wf.backendPlanStatus}
          hasPlanId={!!wf.searchParams.get('planId')}
          onCreateWorkflow={wf.handleCreateWorkflow}
          onSelectWorkflow={wf.handleSelectWorkflow}
          onSelectPlan={wf.handleSelectPlan}
          onLoadWorkflowById={wf.loadWorkflowById}
          onViewResult={() => wf.setResultModalOpen(true)}
          onResetStuckPlan={wf.handleResetStuckPlan}
        />

        <ExecutionControls
          canUndo={wf.canUndo}
          canRedo={wf.canRedo}
          onUndo={wf.handleUndo}
          onRedo={wf.handleRedo}
          selectedPlan={wf.selectedPlan}
          isRunning={wf.isRunning}
          onDeleteDialogOpen={() => wf.setDeleteDialogOpen(true)}
          currentWorkflowId={wf.currentWorkflowId}
          publishPending={wf.publishWorkflowMutation.isPending}
          archivePending={wf.archiveWorkflowMutation.isPending}
          deletePending={wf.deleteWorkflowMutation.isPending}
          onPublish={wf.handlePublishCustomWorkflow}
          onArchive={wf.handleArchiveCustomWorkflow}
          onDeleteCustomWorkflow={wf.handleDeleteCustomWorkflow}
          onOpenShare={wf.handleOpenShare}
          selectedWorkflowName={wf.selectedWorkflow?.name}
          workflowStatus={wf.workflowStatus}
          currentStep={wf.currentStep}
          totalSteps={wf.totalSteps}
          validateOnRun={wf.validateOnRun}
          onValidateOnRunChange={wf.setValidateOnRun}
          onReset={wf.handleResetWorkflow}
          onSave={wf.handleSave}
          onSaveAsTemplate={wf.handleSaveAsTemplate}
          onRun={wf.handleRunWorkflow}
          onStop={wf.handleStopWorkflow}
          isAIGenerated={wf.isAIGenerated}
        />
      </header>

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-h-0">
        <div className="flex-1 flex min-h-0">
          {/* Canvas */}
          <div className="flex-1 min-w-0 relative workflow-canvas" aria-label="Workflow canvas">
            <WorkflowCanvas
              nodes={wf.nodes}
              connections={wf.connections}
              onNodesChange={wf.handleNodesChange}
              onConnectionsChange={wf.handleConnectionsChange}
              onNodeSelect={wf.setSelectedNodeIds}
              selectedNodeIds={wf.selectedNodeIds}
              runningNodeId={wf.runningNodeId}
              onRunNode={wf.handleRunNode}
              onDeleteNode={wf.handleDeleteNode}
              onDuplicateNodes={wf.handleDuplicateNodes}
              onCopyNodes={wf.handleCopyNodes}
              onPasteNodes={wf.handlePasteNodes}
              hasClipboard={!!wf.clipboard}
              onOpenNodeProperties={wf.handleOpenNodeProperties}
              onSaveAsTemplate={wf.handleSaveAsTemplate}
              pendingApproval={wf.pendingApproval}
              onClearPendingApproval={wf.clearPendingApproval}
            />
          </div>

          {/* Right Panel - Unified Context Panel (Agents | Inspector | Scenarios | History) */}
          <CollapsiblePanel
            position="right"
            collapsed={wf.sidebarCollapsed}
            onToggleCollapse={() => wf.setSidebarCollapsed(!wf.sidebarCollapsed)}
            expandedWidth={wf.sidebarWidth}
          >
            <UnifiedContextPanel
              selectedNode={wf.selectedNode ? {
                id: wf.selectedNode.id,
                label: wf.selectedNode.label,
                nodeType: wf.selectedNode.type as string,
                description: wf.selectedNode.description,
                status: wf.selectedNode.status || 'idle',
              } : null}
              onUpdateNode={(id, updates) => wf.handleUpdateNode(id, updates as Partial<WorkflowNode>)}
              onDeleteNode={wf.handleDeleteNode}
              onRunNode={wf.handleRunNode}
              onCloseInspector={() => wf.setSelectedNodeIds([])}
              width={wf.sidebarWidth}
              onWidthChange={wf.setSidebarWidth}
              workflows={wf.workflows}
              userPlans={wf.userPlans}
              myWorkflows={wf.myWorkflows}
              workflowsLoading={wf.workflowsLoading}
              selectedWorkflowId={wf.selectedWorkflowId}
              selectedPlan={wf.selectedPlan}
              currentWorkflowId={wf.currentWorkflowId}
              onCreateWorkflow={wf.handleCreateWorkflow}
              onSelectWorkflow={wf.handleSelectWorkflow}
              onSelectPlan={wf.handleSelectPlan}
              onLoadWorkflowById={wf.loadWorkflowById}
              scenarioName={wf.selectedWorkflow?.name ?? null}
              planId={wf.selectedPlan?.id ?? (wf.searchParams.get('planId') ? Number(wf.searchParams.get('planId')) : null)}
              currentExecutionId={wf.executionId}
              onViewResult={() => wf.setResultModalOpen(true)}
            />
            <PluginSlot
              name="workflow-sidebar"
              hostData={{
                workflowId: wf.selectedWorkflow?.name,
                isDirty: wf.isDirty,
              }}
              className="mt-4"
            />
          </CollapsiblePanel>
        </div>

        {/* Execution Log Toggle Bar — always visible, click to expand/collapse */}
        <div className="border-t border-border shrink-0">
          <button
            onClick={() => wf.setLogCollapsed(!wf.logCollapsed)}
            className="flex items-center gap-2 w-full px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground hover:bg-secondary/30 transition-colors bg-card/30"
            aria-expanded={!wf.logCollapsed}
            aria-label="Toggle execution log"
          >
            <Terminal size={12} />
            <span className="font-medium">Execution Log</span>
            {wf.executionEvents.length > 0 && (
              <span className="px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground text-[10px] tabular-nums">
                {wf.executionEvents.length}
              </span>
            )}
            {wf.isRunning && (
              <span className="flex items-center gap-1 text-primary ml-1">
                <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
                Running
              </span>
            )}
            <span className="ml-auto">
              {wf.logCollapsed ? <ChevronDown size={12} /> : <ChevronUp size={12} />}
            </span>
          </button>

          {/* Execution Log Panel */}
          {!wf.logCollapsed && (
            <ExecutionLog
              events={wf.executionEvents}
              maxHeight={200}
              isCollapsed={false}
            />
          )}
        </div>
      </div>

      {/* Modals and Dialogs */}
      <WorkflowInputModal
        open={wf.inputModalOpen}
        onOpenChange={wf.setInputModalOpen}
        workflowName={wf.selectedWorkflow?.name || t('defaultWorkflowName')}
        inputs={wf.scenarioInputs}
        onSubmit={wf.handleInputSubmit}
        isLoading={wf.isRunning}
      />

      <ExecutionResultModal
        open={wf.resultModalOpen}
        onOpenChange={wf.setResultModalOpen}
        result={wf.workflowResult}
        workflowName={wf.selectedWorkflow?.name}
        status={wf.workflowStatus}
      />

      {/* Delete Plan Confirmation */}
      <AlertDialog open={wf.deleteDialogOpen} onOpenChange={wf.setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('deletePlan.title')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('deletePlan.description', { name: wf.selectedPlan?.name })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={wf.isDeleting}>{t('deletePlan.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={wf.handleDeleteWorkflow}
              disabled={wf.isDeleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {wf.isDeleting ? t('deletePlan.deleting') : t('deletePlan.delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Create Workflow Dialog */}
      <Dialog open={wf.showCreateDialog} onOpenChange={wf.setShowCreateDialog}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>{t('createDialog.title')}</DialogTitle>
            <DialogDescription>
              {t('createDialog.description')}
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="workflow-name">{t('createDialog.nameLabel')}</Label>
              <Input
                id="workflow-name"
                value={wf.newWorkflowName}
                onChange={(e) => wf.setNewWorkflowName(e.target.value)}
                placeholder={t('createDialog.namePlaceholder')}
                aria-label="Workflow name"
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && wf.newWorkflowName.trim() && !wf.isCreating) {
                    wf.handleCreateWorkflowSubmit();
                  }
                }}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="workflow-description">{t('createDialog.descriptionLabel')}</Label>
              <Textarea
                id="workflow-description"
                value={wf.newWorkflowDescription}
                onChange={(e) => wf.setNewWorkflowDescription(e.target.value)}
                placeholder={t('createDialog.descriptionPlaceholder')}
                aria-label="Workflow description"
                rows={3}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => wf.setShowCreateDialog(false)}>
              {t('createDialog.cancel')}
            </Button>
            <Button
              onClick={wf.handleCreateWorkflowSubmit}
              disabled={!wf.newWorkflowName.trim() || wf.isCreating}
            >
              {wf.isCreating ? (
                <>
                  <Loader2 size={14} className="mr-2 motion-safe:animate-spin" aria-hidden="true" />
                  {t('createDialog.creating')}
                </>
              ) : (
                t('createDialog.create')
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Share Workflow Dialog */}
      <Dialog open={wf.showShareDialog} onOpenChange={wf.setShowShareDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t('shareDialog.title')}</DialogTitle>
            <DialogDescription>
              {t('shareDialog.description')}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="share-user-id" className="text-sm">{t('shareDialog.userIdLabel')}</Label>
              <div className="flex gap-2">
                <Input
                  id="share-user-id"
                  value={wf.shareEmail}
                  onChange={(e) => wf.setShareEmail(e.target.value)}
                  placeholder={t('shareDialog.userIdPlaceholder')}
                  aria-label="User ID to share with"
                  className="flex-1"
                />
                <select
                  value={wf.sharePermission}
                  onChange={(e) => wf.setSharePermission(e.target.value as 'view' | 'edit')}
                  aria-label="Share permission level"
                  className="h-10 px-3 rounded-md border border-input bg-background text-sm"
                >
                  <option value="view">{t('shareDialog.permissionView')}</option>
                  <option value="edit">{t('shareDialog.permissionEdit')}</option>
                </select>
              </div>
              {wf.shareError && (
                <p className="text-xs text-destructive" role="alert">{wf.shareError}</p>
              )}
            </div>

            <Button
              onClick={wf.handleShare}
              disabled={!wf.shareEmail.trim()}
              className="w-full"
            >
              <Share2 size={14} className="mr-2" aria-hidden="true" />
              {t('shareDialog.shareButton')}
            </Button>

            {wf.currentShares.length > 0 && (
              <div className="space-y-2">
                <Label className="text-sm">{t('shareDialog.currentShares')}</Label>
                <div className="space-y-1 max-h-[200px] overflow-y-auto">
                  {wf.currentShares.map((share) => (
                    <div
                      key={share.user_id}
                      className="flex items-center justify-between p-2 rounded-md bg-secondary/30"
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="text-sm truncate">{share.user_id}</span>
                        <Badge variant="outline" className="text-[10px] shrink-0">
                          {share.permission}
                        </Badge>
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-muted-foreground hover:text-destructive shrink-0"
                        onClick={() => wf.handleUnshare(share.user_id)}
                        aria-label={`Remove ${share.user_id} from shares`}
                      >
                        <UserX size={14} aria-hidden="true" />
                      </Button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {wf.currentShares.length === 0 && (
              <p className="text-xs text-muted-foreground text-center py-2">
                {t('shareDialog.notSharedYet')}
              </p>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => wf.setShowShareDialog(false)}>
              {t('shareDialog.close')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default WorkflowPage;
