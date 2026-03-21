// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { AlertCircle, HelpCircle, Loader2, Play, X } from "lucide-react";
import { cn } from "@/lib/utils";

interface AgentExecutionFormProps {
  agentName: string;
  onExecute: (task: string, context?: Record<string, unknown>) => Promise<void>;
  onCancel: () => void;
  isExecuting: boolean;
}

const AgentExecutionForm = ({ 
  agentName, 
  onExecute, 
  onCancel, 
  isExecuting 
}: AgentExecutionFormProps) => {
  const [task, setTask] = useState("");
  const [contextJson, setContextJson] = useState("");
  const [contextError, setContextError] = useState<string | null>(null);

  const validateContext = (json: string): boolean => {
    if (!json.trim()) return true;
    try {
      const parsed = JSON.parse(json);
      // Prototype pollution protection
      if (typeof parsed === 'object' && parsed !== null) {
        if ('__proto__' in parsed || 'constructor' in parsed || 'prototype' in parsed) {
          setContextError("Dangerous keys not allowed");
          return false;
        }
      }
      setContextError(null);
      return true;
    } catch {
      setContextError("Invalid JSON format");
      return false;
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!task.trim()) return;
    if (!validateContext(contextJson)) return;

    const context = contextJson.trim() ? JSON.parse(contextJson) : undefined;
    await onExecute(task, context);
  };

  const charCount = task.length;
  const isValid = task.trim().length >= 1 && task.length <= 500 && !contextError;

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label htmlFor="task">Task *</Label>
          <span className={cn(
            "text-xs",
            charCount > 500 ? "text-destructive" : "text-muted-foreground"
          )}>
            {charCount}/500
          </span>
        </div>
        <Textarea
          id="task"
          value={task}
          onChange={(e) => setTask(e.target.value)}
          placeholder={`Describe the task for ${agentName}...`}
          className="min-h-[100px] resize-none"
          required
          maxLength={500}
          disabled={isExecuting}
        />
      </div>

      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <Label htmlFor="context">Context</Label>
          <span className="text-xs text-muted-foreground font-normal">(optional)</span>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <button type="button" className="text-muted-foreground hover:text-foreground">
                  <HelpCircle size={14} />
                </button>
              </TooltipTrigger>
              <TooltipContent side="top" className="max-w-[280px]">
                <p className="text-sm">
                  Additional data the agent can use during execution.
                  Enter as JSON, e.g., {`{"project_id": "abc123"}`}
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  Use this to pass specific values like IDs, file paths, or configuration that the agent needs.
                </p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
        <Textarea
          id="context"
          value={contextJson}
          onChange={(e) => {
            setContextJson(e.target.value);
            if (e.target.value) validateContext(e.target.value);
            else setContextError(null);
          }}
          placeholder='{"key": "value"}'
          className={cn(
            "min-h-[80px] resize-none font-mono text-sm",
            contextError && "border-destructive focus-visible:ring-destructive"
          )}
          disabled={isExecuting}
        />
        {contextError && (
          <p className="text-xs text-destructive flex items-center gap-1">
            <AlertCircle size={12} />
            {contextError}
          </p>
        )}
      </div>

      <div className="flex gap-2 pt-2">
        <Button
          type="button"
          variant="outline"
          onClick={onCancel}
          disabled={isExecuting}
          className="flex-1"
        >
          <X size={16} className="mr-2" />
          Cancel
        </Button>
        <Button
          type="submit"
          disabled={!isValid || isExecuting}
          className="flex-1"
        >
          {isExecuting ? (
            <>
              <Loader2 size={16} className="mr-2 animate-spin" />
              Executing...
            </>
          ) : (
            <>
              <Play size={16} className="mr-2" />
              Execute
            </>
          )}
        </Button>
      </div>
    </form>
  );
};

export default AgentExecutionForm;
