// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// WizardProgress -- horizontal step indicator for the onboarding wizard
// Shows step numbers, names, completion status, and required/optional labels

import { cn } from "@/lib/utils";
import { Check } from "lucide-react";

export interface WizardStep {
  id: string;
  name: string;
  required: boolean;
}

interface WizardProgressProps {
  steps: WizardStep[];
  currentIndex: number;
  completedSteps: Set<string>;
}

const WizardProgress = ({ steps, currentIndex, completedSteps }: WizardProgressProps) => {
  return (
    <nav aria-label="Setup progress" className="flex items-center justify-center gap-1 sm:gap-2">
      {steps.map((step, index) => {
        const isCompleted = completedSteps.has(step.id);
        const isCurrent = index === currentIndex;
        const isPast = index < currentIndex;

        return (
          <div key={step.id} className="flex items-center">
            {/* Step indicator */}
            <div className="flex flex-col items-center gap-1">
              <div
                className={cn(
                  "flex h-8 w-8 items-center justify-center rounded-full text-xs font-semibold transition-all duration-300",
                  isCompleted && "bg-primary text-primary-foreground shadow-glow-sm",
                  isCurrent && !isCompleted && "bg-primary/20 text-primary ring-2 ring-primary",
                  !isCurrent && !isCompleted && "bg-muted text-muted-foreground"
                )}
              >
                {isCompleted ? (
                  <Check className="h-4 w-4" />
                ) : (
                  <span>{index + 1}</span>
                )}
              </div>
              <span
                className={cn(
                  "text-[10px] leading-tight max-w-[60px] text-center hidden sm:block",
                  isCurrent ? "text-foreground font-medium" : "text-muted-foreground"
                )}
              >
                {step.name}
                {!step.required && (
                  <span className="block text-[9px] text-muted-foreground/60 italic">optional</span>
                )}
              </span>
            </div>

            {/* Connector line */}
            {index < steps.length - 1 && (
              <div
                className={cn(
                  "mx-1 h-0.5 w-4 sm:w-8 transition-colors duration-300",
                  isPast || isCompleted ? "bg-primary" : "bg-muted"
                )}
              />
            )}
          </div>
        );
      })}
    </nav>
  );
};

export default WizardProgress;
