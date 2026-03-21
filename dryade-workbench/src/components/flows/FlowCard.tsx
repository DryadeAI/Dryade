// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import {
  Play,
  Square,
  Clock,
  CheckCircle2,
  XCircle,
  Pause,
  RefreshCw,
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import type { FlowStatus } from "@/types/api";

interface FlowCardProps {
  id: string;
  name: string;
  description?: string;
  status: FlowStatus;
  nodeCount: number;
  lastRun?: string;
  progress?: number;
  onSelect: (id: string) => void;
  onExecute: (id: string) => void;
  onStop?: (id: string) => void;
  isSelected?: boolean;
  className?: string;
}

const statusConfig: Record<
  FlowStatus,
  { icon: typeof Clock; color: string; bgColor: string; label: string }
> = {
  idle: {
    icon: Clock,
    color: "text-muted-foreground",
    bgColor: "bg-muted",
    label: "Idle",
  },
  running: {
    icon: Play,
    color: "text-primary",
    bgColor: "bg-primary/10",
    label: "Running",
  },
  complete: {
    icon: CheckCircle2,
    color: "text-success",
    bgColor: "bg-success/10",
    label: "Complete",
  },
  error: {
    icon: XCircle,
    color: "text-destructive",
    bgColor: "bg-destructive/10",
    label: "Error",
  },
};

const FlowCard = ({
  id,
  name,
  description,
  status,
  nodeCount,
  lastRun,
  progress,
  onSelect,
  onExecute,
  onStop,
  isSelected = false,
  className,
}: FlowCardProps) => {
  const config = statusConfig[status];
  const StatusIcon = config.icon;

  return (
    <Card
      className={cn(
        "cursor-pointer transition-all hover:shadow-md",
        isSelected && "ring-2 ring-primary",
        className
      )}
      onClick={() => onSelect(id)}
    >
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <StatusIcon
                className={cn(
                  "w-4 h-4 flex-shrink-0",
                  config.color,
                  status === "running" && "animate-spin"
                )}
              />
              <h3 className="font-medium truncate">{name}</h3>
            </div>
            {description && (
              <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                {description}
              </p>
            )}
          </div>

          <Badge variant="outline" className={cn("flex-shrink-0", config.color)}>
            {config.label}
          </Badge>
        </div>

        {/* Progress bar for running flows */}
        {status === "running" && progress !== undefined && (
          <div className="mt-3 space-y-1">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>Progress</span>
              <span>{progress}%</span>
            </div>
            <Progress value={progress} className="h-1.5" />
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center justify-between mt-4 pt-3 border-t border-border">
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <span>{nodeCount} nodes</span>
            {lastRun && (
              <>
                <span>•</span>
                <span>
                  {formatDistanceToNow(new Date(lastRun), { addSuffix: true })}
                </span>
              </>
            )}
          </div>

          <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
            {status === "running" && onStop ? (
              <Button
                variant="destructive"
                size="sm"
                className="h-7 px-2"
                onClick={() => onStop(id)}
              >
                <Square className="w-3 h-3 mr-1" />
                Stop
              </Button>
            ) : (
              <Button
                variant="default"
                size="sm"
                className="h-7 px-2"
                onClick={() => onExecute(id)}
                disabled={status === "running"}
              >
                {status === "error" ? (
                  <>
                    <RefreshCw className="w-3 h-3 mr-1" />
                    Retry
                  </>
                ) : (
                  <>
                    <Play className="w-3 h-3 mr-1" />
                    Run
                  </>
                )}
              </Button>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export default FlowCard;
