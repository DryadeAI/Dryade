// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Bookmark, RotateCcw, Clock, CheckCircle2 } from "lucide-react";
import { formatDistanceToNow } from "date-fns";

interface Checkpoint {
  id: string;
  label: string;
  nodeId: string;
  timestamp: string;
  state: Record<string, unknown>;
  isAutomatic?: boolean;
}

interface CheckpointCardProps {
  checkpoint: Checkpoint;
  onRestore: (checkpointId: string) => void;
  isRestoring?: boolean;
  className?: string;
}

const CheckpointCard = ({
  checkpoint,
  onRestore,
  isRestoring = false,
  className,
}: CheckpointCardProps) => {
  return (
    <Card className={cn("border-border/50", className)}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-lg bg-primary/10">
              <Bookmark className="w-4 h-4 text-primary" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <p className="font-medium text-sm truncate">
                  {checkpoint.label}
                </p>
                {checkpoint.isAutomatic && (
                  <Badge variant="secondary" className="text-xs">
                    Auto
                  </Badge>
                )}
              </div>
              <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
                <span className="flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3" />
                  Node: {checkpoint.nodeId}
                </span>
                <span>•</span>
                <span className="flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  {formatDistanceToNow(new Date(checkpoint.timestamp), {
                    addSuffix: true,
                  })}
                </span>
              </div>
            </div>
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={() => onRestore(checkpoint.id)}
            disabled={isRestoring}
            className="flex-shrink-0"
          >
            <RotateCcw
              className={cn("w-4 h-4 mr-1", isRestoring && "animate-spin")}
            />
            {isRestoring ? "Restoring..." : "Restore"}
          </Button>
        </div>

        {/* State preview */}
        <div className="mt-3 p-2 bg-muted/30 rounded text-xs font-mono overflow-x-auto">
          <p className="text-muted-foreground mb-1">State snapshot:</p>
          <pre className="text-foreground/80">
            {JSON.stringify(checkpoint.state, null, 2).slice(0, 200)}
            {JSON.stringify(checkpoint.state).length > 200 && "..."}
          </pre>
        </div>
      </CardContent>
    </Card>
  );
};

export default CheckpointCard;
