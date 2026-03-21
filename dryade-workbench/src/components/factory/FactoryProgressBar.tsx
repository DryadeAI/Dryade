// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// FactoryProgressBar - Progress bar with real WebSocket data or animated fallback
// When wsProgress is provided (from factory_progress WebSocket events), displays real data.
// When wsProgress is null/undefined, falls back to timer-based animation.

import { useState, useEffect, useRef } from "react";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";

const STAGE_LABELS = [
  "Analyzing goal...",
  "Checking for duplicates...",
  "Generating configuration...",
  "Scaffolding artifact...",
  "Registering artifact...",
  "Running tests...",
  "Validating output...",
  "Finalizing...",
];

export interface WsProgressData {
  step: number;
  totalSteps: number;
  percentage: number;
  stepName: string;
  detail?: string;
}

interface FactoryProgressBarProps {
  isActive: boolean;
  artifactName?: string;
  wsProgress?: WsProgressData | null;
}

const FactoryProgressBar = ({
  isActive,
  artifactName,
  wsProgress,
}: FactoryProgressBarProps) => {
  // Timer-based fallback state
  const [timerProgress, setTimerProgress] = useState(5);
  const [stageIndex, setStageIndex] = useState(0);
  const progressTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const stageTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const useWs = wsProgress != null;

  // Animated progress fallback: increment from 5% to ~90% over ~30s, decelerating
  useEffect(() => {
    if (!isActive || useWs) {
      setTimerProgress(5);
      setStageIndex(0);
      if (progressTimer.current) clearInterval(progressTimer.current);
      return;
    }

    progressTimer.current = setInterval(() => {
      setTimerProgress((prev) => {
        if (prev >= 90) return prev;
        const remaining = 90 - prev;
        const increment = Math.max(0.5, remaining * 0.06);
        return Math.min(90, prev + increment);
      });
    }, 500);

    return () => {
      if (progressTimer.current) clearInterval(progressTimer.current);
    };
  }, [isActive, useWs]);

  // Cycle through stage labels every ~3.5s (fallback only)
  useEffect(() => {
    if (!isActive || useWs) return;

    stageTimer.current = setInterval(() => {
      setStageIndex((prev) => (prev + 1) % STAGE_LABELS.length);
    }, 3500);

    return () => {
      if (stageTimer.current) clearInterval(stageTimer.current);
    };
  }, [isActive, useWs]);

  if (!isActive) return null;

  // Resolve displayed values: real WebSocket data or timer fallback
  const displayProgress = useWs ? wsProgress.percentage : timerProgress;
  const isComplete = useWs && wsProgress.percentage >= 100;

  let displayLabel: string;
  if (isComplete) {
    displayLabel = "Complete!";
  } else if (useWs) {
    displayLabel = wsProgress.detail
      ? `${wsProgress.stepName} - ${wsProgress.detail}`
      : wsProgress.stepName;
  } else {
    displayLabel = STAGE_LABELS[stageIndex];
  }

  return (
    <div className="space-y-3">
      {artifactName && (
        <p className="text-sm font-medium text-foreground">
          Creating <span className="text-primary">{artifactName}</span>...
        </p>
      )}
      <Progress
        value={displayProgress}
        className={cn("h-2 [&>div]:bg-success")}
      />
      <p
        className={cn(
          "text-xs text-muted-foreground",
          !isComplete && "animate-pulse"
        )}
      >
        {displayLabel}
        {useWs && !isComplete && (
          <span className="ml-2 text-muted-foreground/60">
            ({wsProgress.step}/{wsProgress.totalSteps})
          </span>
        )}
      </p>
    </div>
  );
};

export default FactoryProgressBar;
