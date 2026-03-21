// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useRef, useEffect, useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  Play,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Clock,
  ChevronDown,
  ChevronUp,
  Pause,
  Activity,
} from "lucide-react";
import type { ExecutionEvent } from "@/types/workflow";

interface ExecutionLogProps {
  events: ExecutionEvent[];
  maxHeight?: number;
  className?: string;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}

// Event type to display config mapping
const eventConfig: Record<string, {
  icon: typeof Play;
  label: string;
  colorClass: string;
  bgClass: string;
}> = {
  workflow_start: { icon: Play, label: "Workflow Started", colorClass: "text-primary", bgClass: "bg-primary/10" },
  start: { icon: Play, label: "Workflow Started", colorClass: "text-primary", bgClass: "bg-primary/10" },
  node_start: { icon: Activity, label: "Node Started", colorClass: "text-blue-500", bgClass: "bg-blue-500/10" },
  node_complete: { icon: CheckCircle2, label: "Node Complete", colorClass: "text-success", bgClass: "bg-success/10" },
  checkpoint: { icon: Pause, label: "Checkpoint", colorClass: "text-amber-500", bgClass: "bg-amber-500/10" },
  error: { icon: XCircle, label: "Error", colorClass: "text-destructive", bgClass: "bg-destructive/10" },
  workflow_complete: { icon: CheckCircle2, label: "Workflow Complete", colorClass: "text-success", bgClass: "bg-success/10" },
  complete: { icon: CheckCircle2, label: "Workflow Complete", colorClass: "text-success", bgClass: "bg-success/10" },
};

const formatTimestamp = (timestamp: string) => {
  try {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  } catch {
    return timestamp;
  }
};

const LogEntry = ({ event }: { event: ExecutionEvent }) => {
  const config = eventConfig[event.type] || {
    icon: AlertCircle,
    label: event.type,
    colorClass: "text-muted-foreground",
    bgClass: "bg-muted",
  };
  const Icon = config.icon;

  return (
    <div
      className={cn(
        "flex items-start gap-3 px-3 py-2 rounded-md transition-colors",
        "hover:bg-secondary/30",
        event.type === 'error' && "bg-destructive/5"
      )}
      data-testid="log-entry"
      data-event-type={event.type}
    >
      <div className={cn("p-1.5 rounded-md shrink-0", config.bgClass)}>
        <Icon size={14} className={config.colorClass} />
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-foreground">
            {config.label}
          </span>
          {event.node_id && (
            <span className="text-xs px-1.5 py-0.5 rounded bg-muted text-muted-foreground font-mono">
              {event.node_id}
            </span>
          )}
        </div>

        {event.message && (
          <p className="text-xs text-muted-foreground mt-0.5 truncate" data-testid="node-output-preview">
            {event.message}
          </p>
        )}

        {event.error && (
          <p className="text-xs text-destructive mt-0.5">
            {event.error}
          </p>
        )}

        {event.duration_ms !== undefined && (
          <p className="text-xs text-muted-foreground mt-0.5">
            Duration: {event.duration_ms}ms
          </p>
        )}
      </div>

      <span className="text-[10px] text-muted-foreground/70 shrink-0 tabular-nums">
        {formatTimestamp(event.timestamp)}
      </span>
    </div>
  );
};

export const ExecutionLog = ({
  events,
  maxHeight = 300,
  className,
  isCollapsed = false,
  onToggleCollapse,
}: ExecutionLogProps) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  // Auto-scroll to bottom when new events arrive
  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events, autoScroll]);

  // Detect manual scroll to disable auto-scroll
  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    const target = e.currentTarget;
    const isAtBottom = target.scrollHeight - target.scrollTop <= target.clientHeight + 50;
    setAutoScroll(isAtBottom);
  }, []);

  const hasEvents = events.length > 0;
  const lastEvent = hasEvents ? events[events.length - 1] : null;
  const isRunning = lastEvent && !['workflow_complete', 'complete', 'error'].includes(lastEvent.type);

  return (
    <div className={cn("glass-card", className)} data-testid="execution-log">
      {/* Header — only shown when ExecutionLog manages its own collapse */}
      {onToggleCollapse && (
        <div
          className="flex items-center justify-between px-3 py-2 border-b border-border cursor-pointer hover:bg-secondary/30"
          onClick={onToggleCollapse}
          data-testid="execution-log-header"
        >
          <div className="flex items-center gap-2">
            <Clock size={14} className="text-muted-foreground" />
            <span className="text-sm font-medium text-foreground">Execution Log</span>
            {hasEvents && (
              <span className="text-xs px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground">
                {events.length}
              </span>
            )}
            {isRunning && (
              <span className="flex items-center gap-1 text-xs text-primary">
                <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
                Running
              </span>
            )}
          </div>

          <Button variant="ghost" size="icon" className="h-6 w-6">
            {isCollapsed ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
          </Button>
        </div>
      )}

      {/* Log Content */}
      {!isCollapsed && (
        <div
          ref={scrollRef}
          onScroll={handleScroll}
          className="overflow-y-auto"
          style={{ maxHeight }}
          data-testid="execution-log-list"
        >
          {!hasEvents ? (
            <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
              <Clock size={24} className="mb-2 opacity-50" />
              <p className="text-sm">No execution events yet</p>
              <p className="text-xs mt-1">Run the workflow to see events</p>
            </div>
          ) : (
            <div className="py-2 space-y-1">
              {events.map((event, index) => (
                <LogEntry key={`${event.timestamp}-${index}`} event={event} />
              ))}
            </div>
          )}

          {/* Auto-scroll indicator */}
          {hasEvents && !autoScroll && (
            <div className="sticky bottom-0 left-0 right-0 p-2 bg-gradient-to-t from-background to-transparent">
              <Button
                variant="secondary"
                size="sm"
                className="w-full h-7 text-xs"
                onClick={() => {
                  setAutoScroll(true);
                  if (scrollRef.current) {
                    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
                  }
                }}
              >
                <ChevronDown size={12} className="mr-1" />
                Scroll to latest
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default ExecutionLog;
