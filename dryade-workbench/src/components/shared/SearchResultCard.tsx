// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// SearchResultCard - Single search result with score badge
// Based on COMPONENTS-4.md specification

import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FileText, Copy, ExternalLink, ChevronDown, ChevronUp } from "lucide-react";
import { useState } from "react";

interface SearchResultMetadata {
  source_id?: string;
  source_name?: string;
  page?: number;
  chunk_index?: number;
  file_path?: string;
}

interface SearchResultCardProps {
  result: {
    content: string;
    score: number;
    metadata?: SearchResultMetadata;
  };
  onClick?: () => void;
  onCopyToChat?: (content: string) => void;
  expanded?: boolean;
  className?: string;
}

const getScoreConfig = (score: number): { color: string; label: string; bg: string } => {
  if (score >= 0.9) return { color: "text-success", label: "Excellent", bg: "bg-success/10 border-success/30" };
  if (score >= 0.7) return { color: "text-info", label: "Good", bg: "bg-info/10 border-info/30" };
  if (score >= 0.5) return { color: "text-warning", label: "Fair", bg: "bg-warning/10 border-warning/30" };
  return { color: "text-muted-foreground", label: "Low", bg: "bg-muted/50 border-muted" };
};

const SearchResultCard = ({
  result,
  onClick,
  onCopyToChat,
  expanded: initialExpanded = false,
  className,
}: SearchResultCardProps) => {
  const [expanded, setExpanded] = useState(initialExpanded);
  const [copied, setCopied] = useState(false);
  const scoreConfig = getScoreConfig(result.score);

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(result.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error("Failed to copy:", err);
    }
  };

  const handleCopyToChat = (e: React.MouseEvent) => {
    e.stopPropagation();
    onCopyToChat?.(result.content);
  };

  const truncatedContent = result.content.length > 200 && !expanded
    ? result.content.substring(0, 200) + "..."
    : result.content;

  return (
    <Card
      className={cn(
        "cursor-pointer transition-all hover:shadow-md border",
        scoreConfig.bg,
        className
      )}
      onClick={onClick}
      role="article"
      aria-label={`Search result with ${(result.score * 100).toFixed(0)}% match`}
    >
      <CardContent className="p-4 space-y-3">
        {/* Header */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <FileText className="w-4 h-4 text-muted-foreground flex-shrink-0" />
            <span className="text-xs text-muted-foreground truncate">
              {result.metadata?.source_name || "Unknown source"}
              {result.metadata?.page && ` · Page ${result.metadata.page}`}
            </span>
          </div>
          <Badge variant="outline" className={cn("text-xs shrink-0", scoreConfig.color)}>
            {(result.score * 100).toFixed(0)}% · {scoreConfig.label}
          </Badge>
        </div>

        {/* Content */}
        <div className="relative">
          <p className="text-sm leading-relaxed text-foreground">
            {truncatedContent}
          </p>
          {result.content.length > 200 && (
            <Button
              variant="ghost"
              size="sm"
              className="h-6 px-2 mt-1"
              onClick={(e) => {
                e.stopPropagation();
                setExpanded(!expanded);
              }}
            >
              {expanded ? (
                <>
                  <ChevronUp className="w-3 h-3 mr-1" />
                  Show less
                </>
              ) : (
                <>
                  <ChevronDown className="w-3 h-3 mr-1" />
                  Show more
                </>
              )}
            </Button>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1 pt-1">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs"
            onClick={handleCopy}
          >
            <Copy className="w-3 h-3 mr-1" />
            {copied ? "Copied!" : "Copy"}
          </Button>
          {onCopyToChat && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-xs"
              onClick={handleCopyToChat}
            >
              <ExternalLink className="w-3 h-3 mr-1" />
              Use in Chat
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
};

export default SearchResultCard;
