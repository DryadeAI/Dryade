// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { RefreshCw, RotateCcw } from "lucide-react";
import type { CircuitBreaker } from "@/types/extended-api";

interface CircuitBreakerCardProps {
  breaker: CircuitBreaker;
  onReset?: (name: string) => void;
  className?: string;
}

const stateConfig: Record<
  CircuitBreaker["state"],
  { color: string; bgColor: string; label: string }
> = {
  closed: { color: "text-success", bgColor: "bg-success", label: "Closed" },
  open: { color: "text-destructive", bgColor: "bg-destructive", label: "Open" },
  half_open: { color: "text-warning", bgColor: "bg-warning", label: "Half Open" },
};

const CircuitBreakerCard = ({
  breaker,
  onReset,
  className,
}: CircuitBreakerCardProps) => {
  const config = stateConfig[breaker.state];
  const failurePercentage = (breaker.failure_count / breaker.failure_threshold) * 100;

  return (
    <Card className={cn("border-border/50", className)}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <h3 className="font-medium text-sm truncate">{breaker.name}</h3>
              <Badge className={cn("text-xs text-white", config.bgColor)}>
                {config.label}
              </Badge>
            </div>

            <div className="mt-3 space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground">Failure Count</span>
                <span
                  className={cn(
                    "font-medium",
                    breaker.failure_count >= breaker.failure_threshold - 1 &&
                      "text-destructive"
                  )}
                >
                  {breaker.failure_count} / {breaker.failure_threshold}
                </span>
              </div>
              <Progress
                value={failurePercentage}
                className={cn(
                  "h-1.5",
                  failurePercentage >= 80 && "[&>div]:bg-destructive"
                )}
              />
            </div>

            <div className="mt-3 flex items-center gap-4 text-xs text-muted-foreground">
              <span>Timeout: {breaker.timeout_seconds}s</span>
              {breaker.last_failure && (
                <span>
                  Last failure:{" "}
                  {new Date(breaker.last_failure).toLocaleTimeString()}
                </span>
              )}
            </div>
          </div>

          {breaker.state !== "closed" && onReset && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => onReset(breaker.name)}
              className="flex-shrink-0"
            >
              <RotateCcw className="w-4 h-4 mr-1" />
              Reset
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
};

export default CircuitBreakerCard;
