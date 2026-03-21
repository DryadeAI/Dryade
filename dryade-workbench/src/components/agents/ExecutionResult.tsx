// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { 
  Check, 
  Clock, 
  Coins, 
  Copy, 
  ChevronDown, 
  ChevronUp,
  RefreshCw,
  AlertCircle 
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { AgentInvokeResponse } from "@/types/api";

interface ExecutionResultProps {
  result: AgentInvokeResponse;
  onExecuteAgain: () => void;
}

const ExecutionResult = ({ result, onExecuteAgain }: ExecutionResultProps) => {
  const [copied, setCopied] = useState(false);
  const [detailsExpanded, setDetailsExpanded] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(result.result);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="space-y-4">
      {/* Success Banner with status badge */}
      <div className="flex items-center gap-2 p-3 rounded-lg bg-success/10 border border-success/30">
        <Check size={16} className="text-success" />
        <span className="text-sm font-medium text-success">Execution Complete</span>
      </div>

      {/* Result Content (always visible) */}
      <div className="relative">
        <div className="p-4 rounded-lg bg-secondary/50 border border-border/50">
          <p className="text-sm whitespace-pre-wrap">{result.result}</p>
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={handleCopy}
          className="absolute top-2 right-2 h-7 w-7"
        >
          {copied ? <Check size={14} className="text-success" /> : <Copy size={14} />}
        </Button>
      </div>

      {/* Collapsible Details Section */}
      <div className="space-y-2">
        <button
          onClick={() => setDetailsExpanded(!detailsExpanded)}
          className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          {detailsExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          Details
        </button>

        {detailsExpanded && (
          <div className="pl-4 border-l-2 border-border space-y-3">
            {/* Metrics */}
            <div className="flex flex-wrap gap-3 text-sm">
              <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-secondary">
                <Clock size={12} className="text-muted-foreground" />
                <span>{(result.execution_time_ms / 1000).toFixed(2)}s</span>
              </div>
              <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-secondary">
                <span className="text-xs text-muted-foreground">Tokens:</span>
                <span>{result.tokens_used.toLocaleString()}</span>
              </div>
              <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-secondary">
                <Coins size={12} className="text-muted-foreground" />
                <span>${result.cost.toFixed(4)}</span>
              </div>
            </div>

            {/* Tool Calls (if any) */}
            {result.tool_calls.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-medium text-muted-foreground">
                  Tool calls ({result.tool_calls.length})
                </p>
                <div className="space-y-2">
                  {result.tool_calls.map((call, i) => (
                    <div key={i} className="text-sm p-2 rounded bg-secondary/30">
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-mono text-primary">{call.tool}</span>
                        <span className="text-xs text-muted-foreground">{call.duration_ms}ms</span>
                      </div>
                      <p className="text-xs text-muted-foreground">{call.result}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Execute Again */}
      <Button variant="outline" onClick={onExecuteAgain} className="w-full">
        <RefreshCw size={14} className="mr-2" />
        Execute Again
      </Button>
    </div>
  );
};

interface ExecutionErrorProps {
  error: string;
  onRetry: () => void;
}

export const ExecutionError = ({ error, onRetry }: ExecutionErrorProps) => {
  return (
    <div className="space-y-4">
      <div className="p-4 rounded-lg bg-destructive/10 border border-destructive/30">
        <div className="flex items-center gap-2 mb-2">
          <AlertCircle size={16} className="text-destructive" />
          <span className="font-medium text-destructive">Execution Failed</span>
        </div>
        <p className="text-sm text-muted-foreground">{error}</p>
      </div>
      <Button variant="outline" onClick={onRetry} className="w-full">
        <RefreshCw size={14} className="mr-2" />
        Retry
      </Button>
    </div>
  );
};

export default ExecutionResult;
