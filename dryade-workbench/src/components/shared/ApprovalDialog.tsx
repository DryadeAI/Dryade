// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// ApprovalDialog - Plan review and approval modal with timeout
// Based on COMPONENTS-4.md specification

import { useState, useEffect, useCallback } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { AlertTriangle, Check, X, Edit, Clock, DollarSign, Brain } from "lucide-react";
import type { PlanNode, PlanEdge } from "@/types/extended-api";

interface ApprovalDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  plan: {
    name: string;
    nodes: PlanNode[];
    edges?: PlanEdge[];
    reasoning?: string;
    confidence?: number;
  };
  estimatedCost?: number;
  timeout?: number; // Seconds (default: 300 = 5 min)
  onApprove: () => void;
  onReject: () => void;
  onModify?: () => void;
}

const formatTime = (seconds: number): string => {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
};

const ApprovalDialog = ({
  open,
  onOpenChange,
  plan,
  estimatedCost,
  timeout = 300,
  onApprove,
  onReject,
  onModify,
}: ApprovalDialogProps) => {
  const [countdown, setCountdown] = useState(timeout);
  const [isPaused, setIsPaused] = useState(false);

  // Reset countdown when dialog opens
  useEffect(() => {
    if (open) {
      setCountdown(timeout);
      setIsPaused(false);
    }
  }, [open, timeout]);

  // Countdown logic
  useEffect(() => {
    if (!open || isPaused || countdown <= 0) return;

    const interval = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          // Auto-reject on timeout
          onReject();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [open, isPaused, countdown, onReject]);

  const getCountdownColor = (): string => {
    if (countdown <= 30) return "text-destructive";
    if (countdown <= 60) return "text-warning";
    return "text-foreground";
  };

  const handleApprove = useCallback(() => {
    onApprove();
    onOpenChange(false);
  }, [onApprove, onOpenChange]);

  const handleReject = useCallback(() => {
    onReject();
    onOpenChange(false);
  }, [onReject, onOpenChange]);

  const handleModify = useCallback(() => {
    onModify?.();
    onOpenChange(false);
  }, [onModify, onOpenChange]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <div className="flex items-center justify-between">
            <DialogTitle className="flex items-center gap-2">
              <Brain className="w-5 h-5 text-primary" />
              Review Plan: {plan.name}
            </DialogTitle>
            {/* Countdown Timer */}
            <div
              className={cn(
                "flex items-center gap-2 px-3 py-1.5 rounded-lg bg-muted",
                getCountdownColor()
              )}
            >
              <Clock className="w-4 h-4" />
              <span className="font-mono text-lg font-bold">{formatTime(countdown)}</span>
            </div>
          </div>
          <DialogDescription>
            Review the proposed plan below. It will auto-reject if not approved within the time limit.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Confidence & Cost */}
          <div className="flex items-center gap-4">
            {plan.confidence !== undefined && (
              <Badge variant="outline" className="text-sm">
                {(plan.confidence * 100).toFixed(0)}% Confidence
              </Badge>
            )}
            {estimatedCost !== undefined && (
              <span className="flex items-center gap-1 text-sm text-muted-foreground">
                <DollarSign className="w-4 h-4" />
                Est. ${estimatedCost.toFixed(4)}
              </span>
            )}
          </div>

          {/* Reasoning */}
          {plan.reasoning && (
            <div className="p-3 rounded-lg bg-muted/50 border border-border">
              <p className="text-xs text-muted-foreground mb-1 flex items-center gap-1">
                <Brain className="w-3 h-3" /> AI Reasoning
              </p>
              <p className="text-sm">{plan.reasoning}</p>
            </div>
          )}

          {/* Plan Steps */}
          <div>
            <p className="text-sm font-medium mb-2">
              Proposed Steps ({plan.nodes.length})
            </p>
            <ScrollArea className="h-48 rounded-lg border border-border">
              <div className="p-3 space-y-2">
                {plan.nodes.map((node, idx) => (
                  <div
                    key={node.id}
                    className="flex items-start gap-3 p-2 rounded-lg bg-muted/30"
                  >
                    <span className="flex items-center justify-center w-6 h-6 rounded-full bg-primary/10 text-primary text-xs font-medium">
                      {idx + 1}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium">{node.label}</p>
                      {node.description && (
                        <p className="text-xs text-muted-foreground">{node.description}</p>
                      )}
                      {node.agent && (
                        <Badge variant="outline" className="text-[10px] mt-1">
                          Agent: {node.agent}
                        </Badge>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          </div>

          {/* Warning for low time */}
          {countdown <= 60 && (
            <div className="flex items-center gap-2 p-3 rounded-lg bg-warning/10 text-warning">
              <AlertTriangle className="w-4 h-4 flex-shrink-0" />
              <p className="text-sm">
                {countdown <= 30
                  ? "Less than 30 seconds remaining!"
                  : "Less than 1 minute remaining to review."}
              </p>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2">
          <Button
            variant="default"
            className="flex-1"
            onClick={handleApprove}
          >
            <Check className="w-4 h-4 mr-2" />
            Approve
          </Button>
          {onModify && (
            <Button
              variant="outline"
              onClick={handleModify}
            >
              <Edit className="w-4 h-4 mr-2" />
              Modify
            </Button>
          )}
          <Button
            variant="destructive"
            onClick={handleReject}
          >
            <X className="w-4 h-4 mr-2" />
            Reject
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default ApprovalDialog;
