// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState } from "react";
import { cn } from "@/lib/utils";
import { ChevronRight, Server } from "lucide-react";

/**
 * TypeScript interface matching the backend SourcedResult Pydantic model
 * from plugins/enterprise_search/models.py
 */
export interface SourcedResult {
  content: string;
  source_server: string;
  source_tool: string;
  confidence: number;
  metadata?: Record<string, unknown>;
}

export interface ExpandableSourcesProps {
  sources: SourcedResult[];
  searchTimeMs?: number;
}

/** Color class for the confidence bar based on percentage thresholds */
function confidenceColor(confidence: number): string {
  if (confidence >= 0.8) return "bg-green-500";
  if (confidence >= 0.5) return "bg-yellow-500";
  return "bg-red-500";
}

/** Color class for confidence text */
function confidenceTextColor(confidence: number): string {
  if (confidence >= 0.8) return "text-green-600 dark:text-green-400";
  if (confidence >= 0.5) return "text-yellow-600 dark:text-yellow-400";
  return "text-red-600 dark:text-red-400";
}

/**
 * ExpandableSources -- collapsible source attribution panel for enterprise search results.
 *
 * Collapsed (default): shows "Show N sources" toggle with optional search time.
 * Expanded: shows a list of source cards with server name, tool, confidence bar, and content preview.
 */
const ExpandableSources = ({ sources, searchTimeMs }: ExpandableSourcesProps) => {
  const [expanded, setExpanded] = useState(false);

  if (!sources || sources.length === 0) return null;

  return (
    <div className="mt-2 border-t border-border/50 pt-2">
      {/* Toggle button */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        <ChevronRight
          size={14}
          className={cn(
            "shrink-0 transition-transform duration-200",
            expanded && "rotate-90"
          )}
        />
        <span>
          Show {sources.length} source{sources.length !== 1 ? "s" : ""}
        </span>
        {searchTimeMs !== undefined && (
          <span className="text-[10px] text-muted-foreground/70 ml-1">
            {searchTimeMs < 1000
              ? `in ${searchTimeMs.toFixed(0)}ms`
              : `in ${(searchTimeMs / 1000).toFixed(1)}s`}
          </span>
        )}
      </button>

      {/* Expandable sources list */}
      <div
        className={cn(
          "overflow-hidden transition-all duration-200 ease-in-out",
          expanded ? "max-h-[2000px] opacity-100 mt-2" : "max-h-0 opacity-0"
        )}
      >
        <div className="space-y-1.5">
          {sources.map((source, idx) => {
            const pct = Math.round(source.confidence * 100);
            const preview =
              source.content.length > 100
                ? source.content.slice(0, 100) + "..."
                : source.content;

            return (
              <div
                key={`${source.source_server}-${source.source_tool}-${idx}`}
                className="rounded-md border border-border/40 bg-muted/20 px-2.5 py-2 text-xs"
              >
                {/* Server and tool row */}
                <div className="flex items-center gap-2 mb-1">
                  <Server size={12} className="text-muted-foreground shrink-0" />
                  <span className="font-semibold text-foreground truncate">
                    {source.source_server}
                  </span>
                  <span className="font-mono text-[10px] text-muted-foreground bg-muted/50 px-1.5 py-0.5 rounded truncate">
                    {source.source_tool}
                  </span>
                </div>

                {/* Confidence bar */}
                <div className="flex items-center gap-2 mb-1">
                  <div className="flex-1 h-1.5 bg-muted/50 rounded-full overflow-hidden">
                    <div
                      className={cn(
                        "h-full rounded-full transition-all",
                        confidenceColor(source.confidence)
                      )}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <span
                    className={cn(
                      "text-[10px] font-medium tabular-nums w-8 text-right",
                      confidenceTextColor(source.confidence)
                    )}
                  >
                    {pct}%
                  </span>
                </div>

                {/* Content preview */}
                <p className="text-[11px] text-muted-foreground leading-relaxed line-clamp-2">
                  {preview}
                </p>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default ExpandableSources;
