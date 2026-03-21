// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ChevronDown, ChevronUp, Copy, Check } from "lucide-react";

interface ResultPreviewProps {
  result: unknown;
  maxLines?: number;
  className?: string;
}

const formatResult = (result: unknown): string => {
  if (typeof result === 'string') return result;
  if (result === null || result === undefined) return 'No result';
  try {
    return JSON.stringify(result, null, 2);
  } catch {
    return String(result);
  }
};

const ResultPreview = ({
  result,
  maxLines = 15,
  className,
}: ResultPreviewProps) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [isCopied, setIsCopied] = useState(false);

  const formattedResult = formatResult(result);
  const lines = formattedResult.split('\n');
  const needsExpansion = lines.length > maxLines;
  const displayedContent = isExpanded
    ? formattedResult
    : lines.slice(0, maxLines).join('\n');

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(formattedResult);
      setIsCopied(true);
      setTimeout(() => setIsCopied(false), 2000);
    } catch {
      // Ignore copy errors
    }
  };

  // Detect if content looks like JSON or code
  const isStructured = formattedResult.trim().startsWith('{') ||
                       formattedResult.trim().startsWith('[') ||
                       formattedResult.includes('```');

  return (
    <div className={cn("rounded-lg border border-border bg-muted/30", className)}>
      {/* Header with copy button */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border">
        <span className="text-xs font-medium text-muted-foreground">Result</span>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 px-2"
          onClick={handleCopy}
        >
          {isCopied ? (
            <Check className="w-3.5 h-3.5 text-success" />
          ) : (
            <Copy className="w-3.5 h-3.5" />
          )}
        </Button>
      </div>

      {/* Content */}
      <ScrollArea className={cn(isExpanded ? "max-h-96" : "max-h-64")}>
        <pre
          className={cn(
            "p-3 text-sm whitespace-pre-wrap break-words",
            isStructured ? "font-mono" : "font-sans"
          )}
        >
          {displayedContent}
          {!isExpanded && needsExpansion && (
            <span className="text-muted-foreground">...</span>
          )}
        </pre>
      </ScrollArea>

      {/* Expand/Collapse button */}
      {needsExpansion && (
        <div className="px-3 py-2 border-t border-border">
          <Button
            variant="ghost"
            size="sm"
            className="w-full justify-center gap-1 text-xs"
            onClick={() => setIsExpanded(!isExpanded)}
          >
            {isExpanded ? (
              <>
                <ChevronUp className="w-3.5 h-3.5" />
                Show less
              </>
            ) : (
              <>
                <ChevronDown className="w-3.5 h-3.5" />
                Show more ({lines.length - maxLines} more lines)
              </>
            )}
          </Button>
        </div>
      )}
    </div>
  );
};

export default ResultPreview;
