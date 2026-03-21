// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useEffect } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  RotateCcw,
  Save,
  Square,
  Zap,
  CheckCircle2,
  XCircle,
  Loader2,
  Circle,
  ShieldCheck,
  Sparkles,
  Bookmark,
  ChevronDown,
} from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { Badge } from "@/components/ui/badge";

export type WorkflowStatus = "idle" | "running" | "success" | "error";

export interface WorkflowHeaderProps {
  isRunning: boolean;
  workflowStatus: WorkflowStatus;
  currentStep?: number;
  totalSteps?: number;
  validateOnRun?: boolean;
  onValidateOnRunChange?: (value: boolean) => void;
  onReset: () => void;
  onSave: () => void;
  onSaveAsTemplate?: () => void;
  onRun: () => void;
  onStop: () => void;
  compact?: boolean;
  aiGenerated?: boolean;
}

const statusConfig: Record<WorkflowStatus, { icon: typeof Circle; label: string; className: string }> = {
  idle: {
    icon: Circle,
    label: "Ready",
    className: "text-muted-foreground bg-muted/50",
  },
  running: {
    icon: Loader2,
    label: "Running",
    className: "text-primary bg-primary/10 border-primary/30",
  },
  success: {
    icon: CheckCircle2,
    label: "Complete",
    className: "text-success bg-success/10 border-success/30",
  },
  error: {
    icon: XCircle,
    label: "Failed",
    className: "text-destructive bg-destructive/10 border-destructive/30",
  },
};

const WorkflowHeader = ({
  isRunning,
  workflowStatus,
  currentStep,
  totalSteps,
  validateOnRun = true,
  onValidateOnRunChange,
  onReset,
  onSave,
  onSaveAsTemplate,
  onRun,
  onStop,
  compact = false,
  aiGenerated = false,
}: WorkflowHeaderProps) => {
  const status = statusConfig[workflowStatus];
  const StatusIcon = status.icon;

  // Keyboard shortcuts for run/stop
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable) {
        return;
      }

      // Ctrl/Cmd + Enter to run workflow
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && !isRunning) {
        e.preventDefault();
        onRun();
      }

      // Escape to stop running workflow
      if (e.key === "Escape" && isRunning) {
        e.preventDefault();
        onStop();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isRunning, onRun, onStop]);

  // Compact mode only renders the action buttons
  if (compact) {
    return (
      <div className="flex items-center gap-2">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant={validateOnRun ? "secondary" : "ghost"}
              size="sm"
              onClick={() => onValidateOnRunChange?.(!validateOnRun)}
              className={cn(
                "gap-1.5 h-8",
                validateOnRun && "bg-primary/10 text-primary border border-primary/30"
              )}
              aria-pressed={validateOnRun}
            >
              <ShieldCheck size={14} />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            Validate on Run {validateOnRun ? "(On)" : "(Off)"}
          </TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="sm" onClick={onReset} className="h-8">
              <RotateCcw size={14} />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">Reset workflow</TooltipContent>
        </Tooltip>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm" className="h-8 gap-1">
              <Save size={14} />
              <ChevronDown size={12} className="text-muted-foreground" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={onSave} className="gap-2">
              <Save size={14} />
              Save Workflow
            </DropdownMenuItem>
            {onSaveAsTemplate && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={onSaveAsTemplate} className="gap-2">
                  <Bookmark size={14} />
                  Save as Template
                </DropdownMenuItem>
              </>
            )}
          </DropdownMenuContent>
        </DropdownMenu>

        {isRunning ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="destructive" size="sm" onClick={onStop} className="h-8 gap-1.5">
                <Square size={14} />
                Stop
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom">Stop (Esc)</TooltipContent>
          </Tooltip>
        ) : (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="default" size="sm" onClick={onRun} className="h-8 gap-1.5">
                <Zap size={14} />
                Run
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom">Run (⌘↵)</TooltipContent>
          </Tooltip>
        )}
      </div>
    );
  }

  return (
    <header className="flex items-center justify-between gap-4 mb-4 flex-wrap">
      {/* Title + Status */}
      <div className="flex items-center gap-3">
        <h1 className="text-lg sm:text-xl font-semibold text-foreground">Workflow Builder</h1>

        {/* AI Generated Badge */}
        {aiGenerated && (
          <Badge variant="secondary" className="gap-1 text-xs bg-purple-500/10 text-purple-500 border-purple-500/20">
            <Sparkles size={12} />
            AI Generated
          </Badge>
        )}

        {/* Status Badge */}
        <div
          className={cn(
            "flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-medium transition-all duration-300",
            status.className
          )}
          role="status"
          aria-live="polite"
        >
          <StatusIcon
            size={12}
            className={workflowStatus === "running" ? "animate-spin" : undefined}
          />
          <span>{status.label}</span>
          {currentStep !== undefined && totalSteps !== undefined && workflowStatus === "running" && (
            <span className="font-mono opacity-80">
              {currentStep}/{totalSteps}
            </span>
          )}
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex items-center gap-2">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant={validateOnRun ? "secondary" : "ghost"}
              size="sm"
              onClick={() => onValidateOnRunChange?.(!validateOnRun)}
              className={cn(
                "gap-1.5 h-8",
                validateOnRun && "bg-primary/10 text-primary border border-primary/30"
              )}
              aria-pressed={validateOnRun}
            >
              <ShieldCheck size={14} />
              <span className="hidden sm:inline">Validate</span>
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            Validate on Run {validateOnRun ? "(On)" : "(Off)"}
          </TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="sm" onClick={onReset} className="h-8">
              <RotateCcw size={14} />
              <span className="hidden sm:inline">Reset</span>
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">Reset workflow</TooltipContent>
        </Tooltip>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm" className="h-8 gap-1">
              <Save size={14} />
              <span className="hidden sm:inline">Save</span>
              <ChevronDown size={12} className="text-muted-foreground" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={onSave} className="gap-2">
              <Save size={14} />
              Save Workflow
            </DropdownMenuItem>
            {onSaveAsTemplate && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={onSaveAsTemplate} className="gap-2">
                  <Bookmark size={14} />
                  Save as Template
                </DropdownMenuItem>
              </>
            )}
          </DropdownMenuContent>
        </DropdownMenu>

        {isRunning ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="destructive" size="sm" onClick={onStop} className="h-8 gap-1.5">
                <Square size={14} />
                Stop
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom">Stop (Esc)</TooltipContent>
          </Tooltip>
        ) : (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="hero" size="sm" onClick={onRun} className="h-8 gap-1.5">
                <Zap size={14} />
                Run
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom">Run (⌘↵)</TooltipContent>
          </Tooltip>
        )}
      </div>
    </header>
  );
};

export default WorkflowHeader;
