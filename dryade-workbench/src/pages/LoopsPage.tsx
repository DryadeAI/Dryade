// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
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
import LoopStatusBadge from "@/components/loops/LoopStatusBadge";
import LoopCreateModal from "@/components/loops/LoopCreateModal";
import EmptyState from "@/components/shared/EmptyState";
import {
  useLoops,
  useLoopExecutions,
  useDeleteLoop,
  useTriggerLoop,
  usePauseLoop,
  useResumeLoop,
} from "@/hooks/useLoops";
import type { Loop, LoopExecution } from "@/services/api/loops";
import {
  Plus,
  Play,
  Pause,
  RotateCcw,
  Trash2,
  ChevronDown,
  ChevronRight,
  Timer,
  Loader2,
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

const TARGET_TYPE_OPTIONS = [
  { value: "all", label: "All types" },
  { value: "workflow", label: "Workflow" },
  { value: "agent", label: "Agent" },
  { value: "skill", label: "Skill" },
  { value: "orchestrator_task", label: "Orchestrator Task" },
];

const ENABLED_OPTIONS = [
  { value: "all", label: "All states" },
  { value: "true", label: "Active" },
  { value: "false", label: "Paused" },
];

const LoopsPage = () => {
  const [createOpen, setCreateOpen] = useState(false);
  const [targetFilter, setTargetFilter] = useState("all");
  const [enabledFilter, setEnabledFilter] = useState("all");
  const [expandedLoop, setExpandedLoop] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Loop | null>(null);

  const filters = {
    target_type: targetFilter !== "all" ? targetFilter : undefined,
    enabled: enabledFilter !== "all" ? enabledFilter === "true" : undefined,
  };

  const { data, isLoading } = useLoops(filters);
  const deleteLoop = useDeleteLoop();
  const triggerLoop = useTriggerLoop();
  const pauseLoop = usePauseLoop();
  const resumeLoop = useResumeLoop();

  const loops = data?.items ?? [];

  const handleTrigger = async (loop: Loop) => {
    try {
      await triggerLoop.mutateAsync(loop.id);
      toast.success(`Loop "${loop.name}" triggered.`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Trigger failed.");
    }
  };

  const handlePauseResume = async (loop: Loop) => {
    try {
      if (loop.enabled) {
        await pauseLoop.mutateAsync(loop.id);
        toast.success(`Loop "${loop.name}" paused.`);
      } else {
        await resumeLoop.mutateAsync(loop.id);
        toast.success(`Loop "${loop.name}" resumed.`);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed.");
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteLoop.mutateAsync(deleteTarget.id);
      toast.success(`Loop "${deleteTarget.name}" deleted.`);
      setDeleteTarget(null);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Delete failed.");
    }
  };

  const toggleExpand = (loopId: string) => {
    setExpandedLoop((prev) => (prev === loopId ? null : loopId));
  };

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto" data-testid="loops-container">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Scheduled Loops</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Schedule workflows, agents, skills, and tasks to run automatically.
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          New Loop
        </Button>
      </div>

      {/* Filters */}
      <div className="flex gap-3">
        <Select value={targetFilter} onValueChange={setTargetFilter}>
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="Target type" />
          </SelectTrigger>
          <SelectContent>
            {TARGET_TYPE_OPTIONS.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={enabledFilter} onValueChange={setEnabledFilter}>
          <SelectTrigger className="w-[150px]">
            <SelectValue placeholder="State" />
          </SelectTrigger>
          <SelectContent>
            {ENABLED_OPTIONS.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Loop List */}
      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : loops.length === 0 ? (
        <EmptyState
          icon={<Timer className="h-12 w-12 text-muted-foreground" />}
          title="No scheduled loops"
          description="Create a loop to schedule workflows, agents, or skills to run automatically."
        />
      ) : (
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8" />
                <TableHead>Name</TableHead>
                <TableHead>Target</TableHead>
                <TableHead>Schedule</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loops.map((loop) => (
                <LoopRow
                  key={loop.id}
                  loop={loop}
                  expanded={expandedLoop === loop.id}
                  onToggleExpand={() => toggleExpand(loop.id)}
                  onTrigger={() => handleTrigger(loop)}
                  onPauseResume={() => handlePauseResume(loop)}
                  onDelete={() => setDeleteTarget(loop)}
                  isTriggerPending={triggerLoop.isPending}
                />
              ))}
            </TableBody>
          </Table>
        </Card>
      )}

      {/* Create Modal */}
      <LoopCreateModal open={createOpen} onOpenChange={setCreateOpen} />

      {/* Delete Confirmation */}
      <AlertDialog open={!!deleteTarget} onOpenChange={() => setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete loop?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete &quot;{deleteTarget?.name}&quot; and cancel its
              scheduled job. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};

// ============================================================================
// Loop Row + Execution History Expansion
// ============================================================================

interface LoopRowProps {
  loop: Loop;
  expanded: boolean;
  onToggleExpand: () => void;
  onTrigger: () => void;
  onPauseResume: () => void;
  onDelete: () => void;
  isTriggerPending: boolean;
}

function LoopRow({
  loop,
  expanded,
  onToggleExpand,
  onTrigger,
  onPauseResume,
  onDelete,
  isTriggerPending,
}: LoopRowProps) {
  return (
    <>
      <TableRow className="cursor-pointer" onClick={onToggleExpand}>
        <TableCell>
          {expanded ? (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          )}
        </TableCell>
        <TableCell className="font-medium">{loop.name}</TableCell>
        <TableCell>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-xs capitalize">
              {loop.target_type.replace("_", " ")}
            </Badge>
            <span className="text-sm text-muted-foreground truncate max-w-[200px]">
              {loop.target_id}
            </span>
          </div>
        </TableCell>
        <TableCell>
          <code className="text-xs bg-muted px-1.5 py-0.5 rounded">{loop.schedule}</code>
          <span className="text-xs text-muted-foreground ml-1.5 capitalize">
            ({loop.trigger_type})
          </span>
        </TableCell>
        <TableCell>
          <LoopStatusBadge loop={loop} />
        </TableCell>
        <TableCell className="text-right">
          <div className="flex items-center justify-end gap-1" onClick={(e) => e.stopPropagation()}>
            <Button
              variant="ghost"
              size="icon"
              title="Trigger now"
              onClick={onTrigger}
              disabled={isTriggerPending}
            >
              <Play className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              title={loop.enabled ? "Pause" : "Resume"}
              onClick={onPauseResume}
            >
              {loop.enabled ? (
                <Pause className="h-4 w-4" />
              ) : (
                <RotateCcw className="h-4 w-4" />
              )}
            </Button>
            <Button
              variant="ghost"
              size="icon"
              title="Delete"
              onClick={onDelete}
              className="text-destructive hover:text-destructive"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </TableCell>
      </TableRow>
      {expanded && (
        <TableRow>
          <TableCell colSpan={6} className="bg-muted/30 p-0">
            <ExecutionHistory loopId={loop.id} />
          </TableCell>
        </TableRow>
      )}
    </>
  );
}

// ============================================================================
// Execution History (expanded inline)
// ============================================================================

function ExecutionHistory({ loopId }: { loopId: string }) {
  const { data, isLoading } = useLoopExecutions(loopId, { limit: 10 });
  const executions = data?.items ?? [];

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-4">
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (executions.length === 0) {
    return (
      <p className="text-sm text-muted-foreground py-4 px-6">No executions yet.</p>
    );
  }

  return (
    <div className="px-6 py-3">
      <p className="text-xs font-medium text-muted-foreground mb-2">
        Recent Executions ({data?.total ?? 0} total)
      </p>
      <div className="space-y-1.5">
        {executions.map((exec) => (
          <ExecutionRow key={exec.id} execution={exec} />
        ))}
      </div>
    </div>
  );
}

function ExecutionRow({ execution }: { execution: LoopExecution }) {
  const statusColors: Record<string, string> = {
    completed: "bg-green-500",
    failed: "bg-red-500",
    running: "bg-yellow-500",
    pending: "bg-blue-500",
    cancelled: "bg-gray-500",
  };

  return (
    <div className="flex items-center gap-3 text-sm py-1">
      <span
        className={cn(
          "w-2 h-2 rounded-full shrink-0",
          statusColors[execution.status] ?? "bg-gray-400"
        )}
      />
      <Badge variant="outline" className="text-xs capitalize">
        {execution.status}
      </Badge>
      <span className="text-xs text-muted-foreground">
        {execution.started_at
          ? new Date(execution.started_at).toLocaleString()
          : "N/A"}
      </span>
      {execution.duration_ms !== null && (
        <span className="text-xs text-muted-foreground">
          {execution.duration_ms}ms
        </span>
      )}
      <span className="text-xs text-muted-foreground capitalize">
        {execution.trigger_source}
      </span>
      {execution.error && (
        <span className="text-xs text-destructive truncate max-w-[300px]" title={execution.error}>
          {execution.error}
        </span>
      )}
    </div>
  );
}

export default LoopsPage;
