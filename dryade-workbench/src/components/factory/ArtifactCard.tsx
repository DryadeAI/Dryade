// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// ArtifactCard - Status card for a single factory-created artifact
// Displays name, type, framework, status, prompt, version, and timestamp
// Supports Update, Rollback, Delete actions and click-to-select for detail view

import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import ArtifactStatusBadge from "./ArtifactStatusBadge";
import { getFrameworkStyle } from "@/config/frameworkConfig";
import { CheckCircle2, MoreVertical, Play, RefreshCw, Trash2, Undo2 } from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import type { FactoryArtifact } from "@/services/api/factory";

const typeLabels: Record<string, string> = {
  agent: "Agent",
  tool: "Tool",
  skill: "Skill",
};

interface ArtifactCardProps {
  artifact: FactoryArtifact;
  onClick?: () => void;
  onDelete?: () => void;
  onUpdate?: (artifact: FactoryArtifact) => void;
  onRollback?: (artifact: FactoryArtifact) => void;
  onApprove?: (artifact: FactoryArtifact) => void;
  onSelect?: (artifact: FactoryArtifact) => void;
}

const ArtifactCard = ({
  artifact,
  onClick,
  onDelete,
  onUpdate,
  onRollback,
  onApprove,
  onSelect,
}: ArtifactCardProps) => {
  const frameworkStyle = getFrameworkStyle(artifact.framework);
  const FrameworkIcon = frameworkStyle.icon;

  const isPending = artifact.status === "pending_approval";
  const hasDropdown = onDelete || onUpdate || (onRollback && artifact.version > 1) || (onApprove && isPending);

  const handleCardClick = () => {
    if (onSelect) {
      onSelect(artifact);
    } else if (onClick) {
      onClick();
    }
  };

  return (
    <Card
      className={cn(
        "transition-all hover:shadow-md hover:border-primary/30 flex flex-col",
        (onSelect || onClick) && "cursor-pointer",
      )}
      onClick={handleCardClick}
    >
      <CardContent className="p-4 flex flex-col flex-1">
        {/* Top row: name + status badge + actions */}
        <div className="flex items-start justify-between gap-2">
          <h3 className="font-medium truncate flex-1">{artifact.name}</h3>
          <div className="flex items-center gap-1.5 shrink-0">
            <ArtifactStatusBadge status={artifact.status} />
            {hasDropdown && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
                  <Button variant="ghost" size="sm" className="h-6 w-6 p-0">
                    <MoreVertical className="w-3.5 h-3.5" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  {onApprove && isPending && (
                    <DropdownMenuItem
                      onClick={(e) => {
                        e.stopPropagation();
                        onApprove(artifact);
                      }}
                    >
                      <Play className="w-4 h-4 mr-2" />
                      Approve & Create
                    </DropdownMenuItem>
                  )}
                  {onUpdate && (
                    <DropdownMenuItem
                      onClick={(e) => {
                        e.stopPropagation();
                        onUpdate(artifact);
                      }}
                    >
                      <RefreshCw className="w-4 h-4 mr-2" />
                      Update
                    </DropdownMenuItem>
                  )}
                  {onRollback && artifact.version > 1 && (
                    <DropdownMenuItem
                      onClick={(e) => {
                        e.stopPropagation();
                        onRollback(artifact);
                      }}
                    >
                      <Undo2 className="w-4 h-4 mr-2" />
                      Rollback
                    </DropdownMenuItem>
                  )}
                  {onDelete && (
                    <>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem
                        className="text-destructive focus:text-destructive"
                        onClick={(e) => {
                          e.stopPropagation();
                          onDelete();
                        }}
                      >
                        <Trash2 className="w-4 h-4 mr-2" />
                        Delete
                      </DropdownMenuItem>
                    </>
                  )}
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          </div>
        </div>

        {/* Second row: type badge + framework badge */}
        <div className="flex items-center gap-2 mt-2">
          <Badge variant="outline" className="text-xs">
            {typeLabels[artifact.artifact_type] ?? artifact.artifact_type}
          </Badge>
          <Badge
            variant="outline"
            className={cn(
              "text-xs gap-1",
              frameworkStyle.color,
              frameworkStyle.borderColor
            )}
          >
            <FrameworkIcon className="w-3 h-3" />
            {frameworkStyle.label}
          </Badge>
        </div>

        {/* Third row: source prompt (truncated) */}
        {artifact.source_prompt && (
          <p className="text-sm text-muted-foreground mt-2 line-clamp-2">
            {artifact.source_prompt}
          </p>
        )}

        {/* Bottom row: version + test indicator + timestamp */}
        <div className="flex items-center justify-between mt-auto pt-3 border-t border-border">
          <div className="flex items-center gap-2">
            <Badge variant="secondary" className="text-xs">
              v{artifact.version}
            </Badge>
            {artifact.test_passed && artifact.status === "active" && (
              <span className="inline-flex items-center gap-1 text-xs text-success">
                <CheckCircle2 className="w-3 h-3" />
                Tests passed
              </span>
            )}
          </div>
          <span className="text-xs text-muted-foreground">
            {formatDistanceToNow(new Date(artifact.updated_at), {
              addSuffix: true,
            })}
          </span>
        </div>
      </CardContent>
    </Card>
  );
};

export default ArtifactCard;
