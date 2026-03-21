// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useRef, useEffect } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Search, Download, Lock, Unlock, X } from "lucide-react";
import { formatDistanceToNow } from "date-fns";

type LogLevel = "debug" | "info" | "warn" | "error";

interface LogEntry {
  id: string;
  timestamp: string;
  level: LogLevel;
  nodeId?: string;
  message: string;
  data?: Record<string, unknown>;
}

interface ExecutionLogViewerProps {
  logs: LogEntry[];
  isStreaming?: boolean;
  className?: string;
}

const levelConfig: Record<LogLevel, { color: string; bgColor: string }> = {
  debug: { color: "text-muted-foreground", bgColor: "bg-muted/30" },
  info: { color: "text-primary", bgColor: "bg-primary/10" },
  warn: { color: "text-warning", bgColor: "bg-warning/10" },
  error: { color: "text-destructive", bgColor: "bg-destructive/10" },
};

const ExecutionLogViewer = ({
  logs,
  isStreaming = false,
  className,
}: ExecutionLogViewerProps) => {
  const [searchQuery, setSearchQuery] = useState("");
  const [levelFilter, setLevelFilter] = useState<LogLevel | "all">("all");
  const [scrollLocked, setScrollLocked] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll when streaming and locked
  useEffect(() => {
    if (scrollLocked && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs, scrollLocked]);

  const filteredLogs = logs.filter((log) => {
    if (levelFilter !== "all" && log.level !== levelFilter) return false;
    if (
      searchQuery &&
      !log.message.toLowerCase().includes(searchQuery.toLowerCase())
    )
      return false;
    return true;
  });

  const handleExport = () => {
    const content = logs
      .map(
        (log) =>
          `[${log.timestamp}] [${log.level.toUpperCase()}] ${log.message}${
            log.data ? "\n" + JSON.stringify(log.data, null, 2) : ""
          }`
      )
      .join("\n\n");
    const blob = new Blob([content], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `execution-logs-${Date.now()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className={cn("flex flex-col h-full", className)}>
      {/* Toolbar */}
      <div className="flex items-center gap-2 p-2 border-b border-border bg-card">
        {/* Search */}
        <div className="relative flex-1">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Filter logs..."
            className="pl-8 h-8"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="absolute right-2 top-1/2 -translate-y-1/2"
            >
              <X className="w-4 h-4 text-muted-foreground" />
            </button>
          )}
        </div>

        {/* Level filter */}
        <Select
          value={levelFilter}
          onValueChange={(v) => setLevelFilter(v as LogLevel | "all")}
        >
          <SelectTrigger className="w-24 h-8">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All</SelectItem>
            <SelectItem value="debug">Debug</SelectItem>
            <SelectItem value="info">Info</SelectItem>
            <SelectItem value="warn">Warn</SelectItem>
            <SelectItem value="error">Error</SelectItem>
          </SelectContent>
        </Select>

        {/* Scroll lock toggle */}
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={() => setScrollLocked(!scrollLocked)}
          title={scrollLocked ? "Scroll locked to bottom" : "Scroll unlocked"}
        >
          {scrollLocked ? (
            <Lock className="w-4 h-4" />
          ) : (
            <Unlock className="w-4 h-4" />
          )}
        </Button>

        {/* Export */}
        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={handleExport}>
          <Download className="w-4 h-4" />
        </Button>
      </div>

      {/* Log entries */}
      <ScrollArea className="flex-1" ref={scrollRef}>
        <div className="p-2 space-y-1 font-mono text-xs">
          {filteredLogs.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              No logs to display
            </div>
          ) : (
            filteredLogs.map((log) => {
              const config = levelConfig[log.level];
              return (
                <div
                  key={log.id}
                  className={cn(
                    "px-2 py-1.5 rounded",
                    config.bgColor
                  )}
                >
                  <div className="flex items-start gap-2">
                    <span className="text-muted-foreground whitespace-nowrap">
                      {formatDistanceToNow(new Date(log.timestamp), {
                        addSuffix: true,
                      })}
                    </span>
                    <Badge
                      variant="outline"
                      className={cn("uppercase text-[10px] px-1", config.color)}
                    >
                      {log.level}
                    </Badge>
                    {log.nodeId && (
                      <Badge variant="secondary" className="text-[10px] px-1">
                        {log.nodeId}
                      </Badge>
                    )}
                    <span className="flex-1 break-all">{log.message}</span>
                  </div>
                  {log.data && (
                    <pre className="mt-1 ml-16 text-muted-foreground overflow-x-auto">
                      {JSON.stringify(log.data, null, 2)}
                    </pre>
                  )}
                </div>
              );
            })
          )}

          {/* Streaming indicator */}
          {isStreaming && (
            <div className="flex items-center gap-2 px-2 py-1.5 text-muted-foreground">
              <span className="animate-pulse">●</span>
              <span>Streaming logs...</span>
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  );
};

export default ExecutionLogViewer;
