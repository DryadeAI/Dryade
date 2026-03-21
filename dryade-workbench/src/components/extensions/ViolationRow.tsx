// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AlertTriangle, Info, AlertCircle, Eye, X } from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import type { SafetyViolation } from "@/types/extended-api";

interface ViolationRowProps {
  violation: SafetyViolation;
  onView?: (id: string) => void;
  onDismiss?: (id: string) => void;
  className?: string;
}

const severityConfig: Record<
  SafetyViolation["severity"],
  { icon: typeof Info; color: string; bgColor: string }
> = {
  low: {
    icon: Info,
    color: "text-muted-foreground",
    bgColor: "bg-muted",
  },
  medium: {
    icon: AlertTriangle,
    color: "text-warning",
    bgColor: "bg-warning/10",
  },
  high: {
    icon: AlertCircle,
    color: "text-destructive",
    bgColor: "bg-destructive/10",
  },
};

const typeLabels: Record<SafetyViolation["type"], string> = {
  validation_failure: "Validation Failed",
  sanitization_event: "Output Sanitized",
};

const ViolationRow = ({
  violation,
  onView,
  onDismiss,
  className,
}: ViolationRowProps) => {
  const config = severityConfig[violation.severity];
  const Icon = config.icon;

  return (
    <div
      className={cn(
        "flex items-start gap-3 p-3 rounded-lg border border-border",
        config.bgColor,
        className
      )}
    >
      <div className="flex-shrink-0 mt-0.5">
        <Icon className={cn("w-4 h-4", config.color)} />
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <Badge variant="outline" className={cn("text-xs", config.color)}>
            {violation.severity.toUpperCase()}
          </Badge>
          <Badge variant="secondary" className="text-xs">
            {typeLabels[violation.type]}
          </Badge>
          <span className="text-xs text-muted-foreground">
            {formatDistanceToNow(new Date(violation.timestamp), {
              addSuffix: true,
            })}
          </span>
        </div>
        <p className="text-sm mt-1 line-clamp-2">{violation.details}</p>
      </div>

      <div className="flex items-center gap-1 flex-shrink-0">
        {onView && (
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={() => onView(violation.id)}
          >
            <Eye className="w-4 h-4" />
          </Button>
        )}
        {onDismiss && (
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={() => onDismiss(violation.id)}
          >
            <X className="w-4 h-4" />
          </Button>
        )}
      </div>
    </div>
  );
};

export default ViolationRow;
