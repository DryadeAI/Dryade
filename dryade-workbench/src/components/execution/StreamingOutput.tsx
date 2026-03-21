// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { cn } from "@/lib/utils";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useEffect, useRef, useState } from "react";
import { AlertCircle } from "lucide-react";

interface StreamingOutputProps {
  content: string;
  isStreaming?: boolean;
  className?: string;
  timeout?: number;
  onCancel?: () => void;
}

const StreamingOutput = ({ content, isStreaming = false, className, timeout = 30000, onCancel }: StreamingOutputProps) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [showTimeoutNotice, setShowTimeoutNotice] = useState(false);
  const lastContentRef = useRef(content);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Auto-scroll to bottom when content updates
  useEffect(() => {
    if (scrollRef.current && isStreaming) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [content, isStreaming]);

  // Track content updates for timeout detection
  useEffect(() => {
    if (!isStreaming) {
      setShowTimeoutNotice(false);
      if (timerRef.current) clearTimeout(timerRef.current);
      return;
    }

    if (content !== lastContentRef.current) {
      lastContentRef.current = content;
      setShowTimeoutNotice(false);
      if (timerRef.current) clearTimeout(timerRef.current);
    }

    timerRef.current = setTimeout(() => {
      if (isStreaming) setShowTimeoutNotice(true);
    }, timeout);

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [content, isStreaming, timeout]);

  if (!content && isStreaming) {
    return (
      <div className={cn("flex items-center gap-2 text-sm text-muted-foreground", className)} role="status">
        <span className="flex gap-1">
          <span className="w-2 h-2 bg-primary rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
          <span className="w-2 h-2 bg-primary rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
          <span className="w-2 h-2 bg-primary rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
        </span>
        <span>Processing...</span>
      </div>
    );
  }

  return (
    <ScrollArea className={cn("max-h-64", className)}>
      <div ref={scrollRef} aria-live="polite" aria-atomic="false">
        <pre className="text-sm font-mono whitespace-pre-wrap break-words p-3 rounded-lg bg-muted/50">
          {content}
          {isStreaming && (
            <span className="inline-block w-2 h-4 bg-primary ml-0.5 animate-pulse" />
          )}
        </pre>
        {showTimeoutNotice && (
          <div className="flex items-center gap-2 mt-2 p-2 rounded-md bg-warning/10 border border-warning/30 text-sm">
            <AlertCircle className="w-4 h-4 text-warning shrink-0" />
            <span className="text-warning">Response may be taking longer than expected.</span>
            {onCancel && (
              <button
                onClick={onCancel}
                className="ml-auto text-xs font-medium text-warning hover:text-warning/80 underline"
              >
                Cancel
              </button>
            )}
          </div>
        )}
      </div>
    </ScrollArea>
  );
};

export default StreamingOutput;
