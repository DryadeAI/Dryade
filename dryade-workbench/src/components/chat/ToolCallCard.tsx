// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
/**
 * Interactive tool call display with view, edit, and re-run capabilities.
 * Respects user preferences for display mode (collapsed/expanded/smart-collapse).
 */
import React, { useState } from "react";
import { useForm } from "react-hook-form";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  ChevronRight,
  Terminal,
  Loader2,
  Edit2,
  RefreshCw,
  Check,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { usePreferences } from "@/hooks/usePreferences";
import { ImageDisplay } from "./ImageDisplay";

type ToolCallStatus = "running" | "complete" | "error";

interface ToolCallCardProps {
  tool: string;
  args: Record<string, unknown>;
  result?: string;
  error?: string;
  status: ToolCallStatus;
  timestamp?: string;
  onRerun?: (args: Record<string, unknown>) => void;
  className?: string;
  /** Image content from MCP tool results (base64 encoded) */
  imageContent?: Array<{ data: string; mimeType: string }>;
}

export const ToolCallCard = React.memo(function ToolCallCard({
  tool,
  args,
  result,
  error,
  status,
  timestamp,
  onRerun,
  className,
  imageContent,
}: ToolCallCardProps) {
  const [editing, setEditing] = useState(false);
  const { preferences } = usePreferences();
  const { agentRuns } = preferences;

  const form = useForm({ defaultValues: args as Record<string, string> });

  // Calculate if output should be collapsed based on preference
  const output = error || result || "";
  const outputLines = output.split("\n").length;
  const shouldCollapse =
    agentRuns.toolCallDisplay === "collapsed" ||
    (agentRuns.toolCallDisplay === "smart-collapse" &&
      outputLines > agentRuns.smartCollapseThreshold);

  const [outputExpanded, setOutputExpanded] = useState(
    agentRuns.toolCallDisplay === "expanded"
  );

  const handleRerun = (data: Record<string, unknown>) => {
    onRerun?.(data);
    setEditing(false);
  };

  const statusBadge = {
    running: (
      <Badge variant="secondary" className="text-xs">
        <Loader2 className="h-3 w-3 animate-spin mr-1" />
        Running
      </Badge>
    ),
    complete: (
      <Badge variant="default" className="text-xs bg-success/20 text-success border-success/50">
        <Check className="h-3 w-3 mr-1" />
        Complete
      </Badge>
    ),
    error: (
      <Badge variant="destructive" className="text-xs">
        <X className="h-3 w-3 mr-1" />
        Error
      </Badge>
    ),
  }[status];

  return (
    <div
      className={cn("border rounded-lg bg-muted/30 overflow-hidden", className)}
    >
      {/* Header */}
      <div className="flex items-center justify-between p-3 bg-muted/50">
        <div className="flex items-center gap-2">
          <Terminal className="h-4 w-4 text-muted-foreground" />
          <span className="font-mono text-sm font-medium">{tool}</span>
          {statusBadge}
        </div>
        <div className="flex items-center gap-1">
          {agentRuns.showTimestamps && timestamp && (
            <span className="text-xs text-muted-foreground mr-2">
              {new Date(timestamp).toLocaleTimeString()}
            </span>
          )}
          {onRerun && status !== "running" && (
            <>
              <Button
                size="icon"
                variant="ghost"
                className="h-7 w-7"
                onClick={() => setEditing(!editing)}
                title="Edit parameters"
              >
                <Edit2 className="h-3.5 w-3.5" />
              </Button>
              <Button
                size="icon"
                variant="ghost"
                className="h-7 w-7"
                onClick={() => onRerun(args)}
                title="Re-run with same parameters"
              >
                <RefreshCw className="h-3.5 w-3.5" />
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Edit mode */}
      {editing ? (
        <form
          onSubmit={form.handleSubmit(handleRerun)}
          className="p-3 space-y-3 border-t"
        >
          <p className="text-xs font-medium text-muted-foreground">
            Edit Parameters
          </p>
          {Object.entries(args).map(([key, value]) => (
            <div key={key} className="space-y-1">
              <Label className="text-xs">{key}</Label>
              <Input
                {...form.register(key)}
                defaultValue={String(value)}
                className="font-mono text-xs h-8"
              />
            </div>
          ))}
          <div className="flex gap-2 pt-2">
            <Button type="submit" size="sm">
              Re-run
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => setEditing(false)}
            >
              Cancel
            </Button>
          </div>
        </form>
      ) : (
        <>
          {/* Arguments display */}
          <div className="p-3 border-t">
            <p className="text-xs font-medium text-muted-foreground mb-2">
              Arguments
            </p>
            <pre className="text-xs font-mono text-muted-foreground overflow-x-auto">
              {agentRuns.showRawOutput
                ? JSON.stringify(args)
                : JSON.stringify(args, null, 2)}
            </pre>
          </div>

          {/* Output display */}
          {output && (
            <Collapsible
              open={!shouldCollapse || outputExpanded}
              onOpenChange={setOutputExpanded}
              className="border-t"
            >
              <CollapsibleTrigger className="flex items-center gap-2 p-3 w-full text-left hover:bg-muted/50">
                <ChevronRight
                  className={cn(
                    "h-3 w-3 transition-transform",
                    outputExpanded && "rotate-90"
                  )}
                />
                <span className="text-xs font-medium text-muted-foreground">
                  {error ? "Error" : "Output"}
                  {shouldCollapse && !outputExpanded && (
                    <span className="ml-2 text-muted-foreground/60">
                      ({outputLines} lines)
                    </span>
                  )}
                </span>
              </CollapsibleTrigger>
              <CollapsibleContent>
                <pre
                  className={cn(
                    "p-3 pt-0 text-xs font-mono whitespace-pre-wrap overflow-x-auto",
                    error && "text-destructive"
                  )}
                >
                  {output}
                </pre>
              </CollapsibleContent>
            </Collapsible>
          )}

          {/* Image content from MCP tool results */}
          {imageContent && imageContent.length > 0 && (
            <div className="p-3 border-t">
              <ImageDisplay images={imageContent} />
            </div>
          )}
        </>
      )}
    </div>
  );
});

export type { ToolCallCardProps, ToolCallStatus };
