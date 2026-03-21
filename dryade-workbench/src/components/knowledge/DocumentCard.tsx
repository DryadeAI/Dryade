// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { 
  FileText, 
  File, 
  FileCode, 
  Trash2, 
  Link2, 
  MoreVertical,
  Loader2,
  CheckCircle,
  AlertCircle
} from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { formatDistanceToNow } from "date-fns";
import type { KnowledgeSource } from "@/types/extended-api";

interface DocumentCardProps {
  source: KnowledgeSource;
  selected?: boolean;
  onSelect?: (id: string) => void;
  onDelete?: (id: string) => void;
  onBind?: (id: string) => void;
  className?: string;
}

const typeIcons: Record<string, typeof FileText> = {
  pdf: FileText,
  md: FileCode,
  text: File,
  docx: FileText,
};

const statusConfig = {
  ready: { icon: CheckCircle, color: "text-success", label: "Ready" },
  processing: { icon: Loader2, color: "text-warning", label: "Processing" },
  error: { icon: AlertCircle, color: "text-destructive", label: "Error" },
};

const DocumentCard = ({
  source,
  selected = false,
  onSelect,
  onDelete,
  onBind,
  className,
}: DocumentCardProps) => {
  const TypeIcon = typeIcons[source.source_type] || File;
  const statusInfo = statusConfig[source.status];
  const StatusIcon = statusInfo.icon;

  const formatSize = (bytes?: number) => {
    if (!bytes) return "—";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <Card
      className={cn(
        "transition-all cursor-pointer hover:border-primary/50",
        selected && "border-primary bg-primary/5 ring-1 ring-primary/20",
        className
      )}
      onClick={() => onSelect?.(source.id)}
    >
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3 min-w-0">
            <div className={cn(
              "p-2 rounded-lg shrink-0",
              source.source_type === "pdf" && "bg-destructive/10",
              source.source_type === "md" && "bg-info/10",
              source.source_type === "text" && "bg-muted",
              source.source_type === "docx" && "bg-accent-secondary/10"
            )}>
              <TypeIcon className={cn(
                "w-5 h-5",
                source.source_type === "pdf" && "text-destructive",
                source.source_type === "md" && "text-info",
                source.source_type === "text" && "text-muted-foreground",
                source.source_type === "docx" && "text-accent-secondary"
              )} />
            </div>
            <div className="min-w-0">
              <p className="font-medium text-sm truncate">{source.name}</p>
              <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
                <span>{source.chunk_count || 0} chunks</span>
                <span>•</span>
                <span>{formatSize(source.size_bytes)}</span>
              </div>
            </div>
          </div>

          <DropdownMenu>
            <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
              <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0">
                <MoreVertical className="w-4 h-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={(e) => { e.stopPropagation(); onBind?.(source.id); }}>
                <Link2 className="w-4 h-4 mr-2" />
                Bind to Agent
              </DropdownMenuItem>
              <DropdownMenuItem
                className="text-destructive"
                onClick={(e) => { e.stopPropagation(); onDelete?.(source.id); }}
              >
                <Trash2 className="w-4 h-4 mr-2" />
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        {/* Status & Progress */}
        <div className="mt-3 flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <StatusIcon 
              className={cn(
                "w-3.5 h-3.5",
                statusInfo.color,
                source.status === "processing" && "animate-spin"
              )} 
            />
            <span className={cn("text-xs", statusInfo.color)}>
              {statusInfo.label}
            </span>
          </div>
          <span className="text-xs text-muted-foreground">
            {formatDistanceToNow(new Date(source.created_at), { addSuffix: true })}
          </span>
        </div>

        {source.status === "processing" && (
          <Progress value={50} className="mt-2 h-1" />
        )}

        {/* Bindings */}
        {(source.crews.length > 0 || source.agents.length > 0) && (
          <div className="mt-3 flex flex-wrap gap-1">
            {source.crews.map((crew) => (
              <Badge key={crew} variant="secondary" className="text-xs">
                {crew}
              </Badge>
            ))}
            {source.agents.map((agent) => (
              <Badge key={agent} variant="outline" className="text-xs">
                {agent}
              </Badge>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default DocumentCard;
