// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import ResultPreview from "./ResultPreview";
import {
  CheckCircle2,
  XCircle,
  AlertCircle,
  Clock,
  ExternalLink,
  RotateCcw,
} from "lucide-react";
import type { ExecutionStatus } from "@/types/execution";

interface CompletionModalProps {
  isOpen: boolean;
  onClose: () => void;
  executionId: string | null;
  scenarioName: string | null;
  status: ExecutionStatus;
  startedAt: string | null;
  completedAt: string | null;
  result: unknown | null;
  error: string | null;
  onRunAgain?: () => void;
}

const statusConfig: Record<ExecutionStatus, {
  icon: typeof CheckCircle2;
  color: string;
  bgColor: string;
  label: string;
}> = {
  running: { icon: Clock, color: "text-primary", bgColor: "bg-primary/10", label: "Running" },
  completed: { icon: CheckCircle2, color: "text-success", bgColor: "bg-success/10", label: "Completed" },
  failed: { icon: XCircle, color: "text-destructive", bgColor: "bg-destructive/10", label: "Failed" },
  cancelled: { icon: AlertCircle, color: "text-amber-500", bgColor: "bg-amber-500/10", label: "Cancelled" },
};

const formatDuration = (startedAt: string | null, completedAt: string | null): string => {
  if (!startedAt || !completedAt) return '-';
  const start = new Date(startedAt).getTime();
  const end = new Date(completedAt).getTime();
  const ms = end - start;

  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  const minutes = Math.floor(ms / 60000);
  const seconds = Math.floor((ms % 60000) / 1000);
  return `${minutes}m ${seconds}s`;
};

const formatScenarioName = (name: string | null): string => {
  if (!name) return 'Workflow';
  return name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
};

const CompletionModal = ({
  isOpen,
  onClose,
  executionId,
  scenarioName,
  status,
  startedAt,
  completedAt,
  result,
  error,
  onRunAgain,
}: CompletionModalProps) => {
  const navigate = useNavigate();
  const config = statusConfig[status] ?? statusConfig.running;
  const StatusIcon = config.icon;
  const duration = formatDuration(startedAt, completedAt);
  const isFailed = status === 'failed';

  // Extract output from result object
  const displayResult = useMemo(() => {
    if (error) return error;
    if (!result) return null;

    // If result has output field (from workflow_complete event)
    if (typeof result === 'object' && result !== null && 'output' in result) {
      return (result as { output: unknown }).output;
    }
    return result;
  }, [result, error]);

  const handleViewDetails = () => {
    if (executionId) {
      navigate(`/workspace/executions/${executionId}`);
    }
    onClose();
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          {/* Status header with icon */}
          <div className="flex items-center gap-4 mb-2">
            <div className={cn(
              "w-14 h-14 rounded-full flex items-center justify-center",
              config.bgColor
            )}>
              <StatusIcon className={cn("w-8 h-8", config.color)} />
            </div>
            <div className="flex-1 min-w-0">
              <DialogTitle className="text-xl truncate">
                {formatScenarioName(scenarioName)}
              </DialogTitle>
              <div className="flex items-center gap-3 mt-1 text-sm text-muted-foreground">
                <span className={cn("font-medium", config.color)}>
                  {config.label}
                </span>
                <span className="flex items-center gap-1">
                  <Clock className="w-3.5 h-3.5" />
                  {duration}
                </span>
              </div>
            </div>
          </div>
        </DialogHeader>

        {/* Result preview */}
        <div className="py-4">
          {displayResult ? (
            <ResultPreview
              result={displayResult}
              className={isFailed ? "border-destructive/50" : undefined}
            />
          ) : (
            <div className="p-4 rounded-lg bg-muted/30 text-center text-sm text-muted-foreground">
              No output available
            </div>
          )}
        </div>

        <DialogFooter className="flex-col sm:flex-row gap-2">
          {/* View Details - Primary */}
          <Button
            variant="default"
            className="w-full sm:w-auto gap-2"
            onClick={handleViewDetails}
          >
            <ExternalLink className="w-4 h-4" />
            View Details
          </Button>

          {/* Run Again - Secondary */}
          {onRunAgain && (
            <Button
              variant="outline"
              className="w-full sm:w-auto gap-2"
              onClick={() => {
                onClose();
                onRunAgain();
              }}
            >
              <RotateCcw className="w-4 h-4" />
              Run Again
            </Button>
          )}

          {/* Close - Tertiary */}
          <Button
            variant="ghost"
            className="w-full sm:w-auto"
            onClick={onClose}
          >
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default CompletionModal;
