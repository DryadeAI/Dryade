// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { Shield, ShieldCheck, ShieldAlert, Lock } from "lucide-react";

type IsolationLevel = "none" | "low" | "medium" | "high" | "strict";

interface IsolationLevelSelectorProps {
  value: IsolationLevel;
  onChange: (value: IsolationLevel) => void;
  disabled?: boolean;
  className?: string;
}

const levelConfig: Record<
  IsolationLevel,
  {
    icon: typeof Shield;
    label: string;
    description: string;
    color: string;
    bgColor: string;
  }
> = {
  none: {
    icon: Shield,
    label: "None",
    description: "No isolation - full system access",
    color: "text-destructive",
    bgColor: "bg-destructive/10",
  },
  low: {
    icon: Shield,
    label: "Low",
    description: "Basic restrictions, network access allowed",
    color: "text-warning",
    bgColor: "bg-warning/10",
  },
  medium: {
    icon: ShieldCheck,
    label: "Medium",
    description: "Limited file access, sandboxed execution",
    color: "text-primary",
    bgColor: "bg-primary/10",
  },
  high: {
    icon: ShieldCheck,
    label: "High",
    description: "Strict sandbox, no network, temp files only",
    color: "text-success",
    bgColor: "bg-success/10",
  },
  strict: {
    icon: Lock,
    label: "Strict",
    description: "Maximum isolation, read-only, no I/O",
    color: "text-success",
    bgColor: "bg-success/10",
  },
};

const IsolationLevelSelector = ({
  value,
  onChange,
  disabled = false,
  className,
}: IsolationLevelSelectorProps) => {
  return (
    <RadioGroup
      value={value}
      onValueChange={(v) => onChange(v as IsolationLevel)}
      disabled={disabled}
      className={cn("space-y-2", className)}
    >
      {(Object.keys(levelConfig) as IsolationLevel[]).map((level) => {
        const config = levelConfig[level];
        const Icon = config.icon;
        const isSelected = value === level;

        return (
          <label
            key={level}
            className={cn(
              "flex items-start gap-3 p-3 rounded-lg border transition-all cursor-pointer",
              isSelected
                ? "border-primary bg-primary/5"
                : "border-border hover:border-primary/50",
              disabled && "opacity-50 cursor-not-allowed"
            )}
          >
            <RadioGroupItem value={level} className="mt-1" />
            <div
              className={cn(
                "p-2 rounded-lg",
                config.bgColor
              )}
            >
              <Icon className={cn("w-4 h-4", config.color)} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-medium text-sm">{config.label}</span>
                {level === "medium" && (
                  <Badge variant="secondary" className="text-xs">
                    Default
                  </Badge>
                )}
                {level === "strict" && (
                  <Badge variant="outline" className="text-xs">
                    Recommended
                  </Badge>
                )}
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                {config.description}
              </p>
            </div>
          </label>
        );
      })}
    </RadioGroup>
  );
};

export default IsolationLevelSelector;
