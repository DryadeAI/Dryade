// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Input } from "@/components/ui/input";
import { 
  Search, 
  ChevronLeft, 
  ChevronRight, 
  Copy, 
  Check,
  FileText,
  Hash
} from "lucide-react";

interface Chunk {
  id: string;
  content: string;
  metadata: {
    page?: number;
    chunk_index: number;
    source_name?: string;
  };
}

interface ChunkViewerProps {
  sourceId: string;
  sourceName: string;
  chunks: Chunk[];
  totalChunks: number;
  onLoadMore?: () => void;
  loading?: boolean;
  className?: string;
}

const ChunkViewer = ({
  sourceId,
  sourceName,
  chunks,
  totalChunks,
  onLoadMore,
  loading = false,
  className,
}: ChunkViewerProps) => {
  const [searchQuery, setSearchQuery] = useState("");
  const [currentIndex, setCurrentIndex] = useState(0);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const filteredChunks = searchQuery
    ? chunks.filter((c) => c.content.toLowerCase().includes(searchQuery.toLowerCase()))
    : chunks;

  const currentChunk = filteredChunks[currentIndex];

  const handleCopy = async (content: string, id: string) => {
    await navigator.clipboard.writeText(content);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handlePrev = () => {
    setCurrentIndex((prev) => Math.max(0, prev - 1));
  };

  const handleNext = () => {
    if (currentIndex < filteredChunks.length - 1) {
      setCurrentIndex((prev) => prev + 1);
    } else if (filteredChunks.length < totalChunks && onLoadMore) {
      onLoadMore();
    }
  };

  const highlightText = (text: string, query: string) => {
    if (!query) return text;
    const parts = text.split(new RegExp(`(${query})`, "gi"));
    return parts.map((part, i) =>
      part.toLowerCase() === query.toLowerCase() ? (
        <mark key={i} className="bg-primary/30 text-foreground rounded px-0.5">
          {part}
        </mark>
      ) : (
        part
      )
    );
  };

  return (
    <Card className={cn("flex flex-col", className)}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FileText className="w-5 h-5 text-muted-foreground" />
            <CardTitle className="text-base">{sourceName}</CardTitle>
          </div>
          <Badge variant="secondary">
            {totalChunks} chunks
          </Badge>
        </div>
        
        {/* Search */}
        <div className="relative mt-3">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setCurrentIndex(0);
            }}
            placeholder="Search within chunks..."
            className="pl-9"
          />
        </div>
      </CardHeader>

      <CardContent className="flex-1 flex flex-col min-h-0">
        {currentChunk ? (
          <>
            {/* Chunk Metadata */}
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Hash className="w-4 h-4" />
                <span>Chunk {currentChunk.metadata.chunk_index + 1}</span>
                {currentChunk.metadata.page !== undefined && (
                  <>
                    <span>•</span>
                    <span>Page {currentChunk.metadata.page}</span>
                  </>
                )}
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => handleCopy(currentChunk.content, currentChunk.id)}
              >
                {copiedId === currentChunk.id ? (
                  <Check className="w-4 h-4 text-success" />
                ) : (
                  <Copy className="w-4 h-4" />
                )}
              </Button>
            </div>

            {/* Chunk Content */}
            <ScrollArea className="flex-1 rounded-lg border bg-muted/30 p-4">
              <p className="text-sm whitespace-pre-wrap leading-relaxed">
                {highlightText(currentChunk.content, searchQuery)}
              </p>
            </ScrollArea>

            {/* Navigation */}
            <div className="flex items-center justify-between mt-4">
              <Button
                variant="outline"
                size="sm"
                onClick={handlePrev}
                disabled={currentIndex === 0}
              >
                <ChevronLeft className="w-4 h-4 mr-1" />
                Previous
              </Button>

              <span className="text-sm text-muted-foreground">
                {currentIndex + 1} of {filteredChunks.length}
                {searchQuery && ` (filtered from ${totalChunks})`}
              </span>

              <Button
                variant="outline"
                size="sm"
                onClick={handleNext}
                disabled={currentIndex >= filteredChunks.length - 1 && filteredChunks.length >= totalChunks}
              >
                Next
                <ChevronRight className="w-4 h-4 ml-1" />
              </Button>
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center text-muted-foreground">
            {loading ? "Loading chunks..." : "No chunks found"}
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default ChunkViewer;
