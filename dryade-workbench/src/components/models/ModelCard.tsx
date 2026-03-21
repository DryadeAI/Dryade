// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { cn } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Star, Clock, Zap, BarChart3, DollarSign, Loader2 } from "lucide-react";
import type { Model, ModelStatus } from "@/types/extended-api";

interface ModelCardProps {
  model: Model;
  selected?: boolean;
  onSelect?: (id: string, selected: boolean) => void;
  onSetDefault?: (id: string) => void;
  showCompareCheckbox?: boolean;
  className?: string;
}

const statusConfig: Record<ModelStatus, { color: string; label: string }> = {
  available: { color: "text-success", label: "Available" },
  loading: { color: "text-warning", label: "Loading" },
  error: { color: "text-destructive", label: "Error" },
  deprecated: { color: "text-muted-foreground", label: "Deprecated" },
};

const ModelCard = ({
  model,
  selected = false,
  onSelect,
  onSetDefault,
  showCompareCheckbox = false,
  className,
}: ModelCardProps) => {
  const config = statusConfig[model.status];

  return (
    <Card
      className={cn(
        "transition-all",
        model.is_default && "border-primary",
        selected && "ring-2 ring-primary",
        className
      )}
    >
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-start gap-2 min-w-0">
            {showCompareCheckbox && onSelect && (
              <Checkbox
                checked={selected}
                onCheckedChange={(checked) => onSelect(model.id, checked === true)}
                className="mt-1"
              />
            )}
            <div className="min-w-0">
              <CardTitle className="text-base flex items-center gap-2">
                <span className="truncate">{model.display_name}</span>
                {model.is_default && (
                  <Star className="w-4 h-4 text-amber-500 fill-amber-500 flex-shrink-0" />
                )}
              </CardTitle>
              <CardDescription>{model.provider}</CardDescription>
            </div>
          </div>
          <Badge variant="outline" className={cn("flex-shrink-0", config.color)}>
            {model.status === "loading" && <Loader2 className="w-3 h-3 mr-1 animate-spin" />}
            {config.label}
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Metrics */}
        {model.metrics && (
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="flex items-center gap-2">
              <Clock className="w-4 h-4 text-muted-foreground" />
              <span>{model.metrics.latency_avg_ms}ms</span>
            </div>
            <div className="flex items-center gap-2">
              <Zap className="w-4 h-4 text-muted-foreground" />
              <span>{model.metrics.tokens_per_second} t/s</span>
            </div>
            <div className="flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-muted-foreground" />
              <span>{model.metrics.success_rate}%</span>
            </div>
            {model.metrics.cost_per_1k_tokens !== undefined && (
              <div className="flex items-center gap-2">
                <DollarSign className="w-4 h-4 text-muted-foreground" />
                <span>${model.metrics.cost_per_1k_tokens}/1k</span>
              </div>
            )}
          </div>
        )}

        {/* Tags */}
        <div className="flex flex-wrap gap-1">
          {model.is_custom && (
            <Badge variant="secondary" className="text-xs">
              Custom
            </Badge>
          )}
          {model.created_at && (
            <Badge variant="outline" className="text-xs text-muted-foreground">
              Created {new Date(model.created_at).toLocaleDateString()}
            </Badge>
          )}
        </div>

        {/* Actions */}
        {!model.is_default && onSetDefault && model.status === "available" && (
          <Button
            variant="outline"
            size="sm"
            className="w-full"
            onClick={() => onSetDefault(model.id)}
          >
            <Star className="w-4 h-4 mr-1" />
            Set as Default
          </Button>
        )}
      </CardContent>
    </Card>
  );
};

export default ModelCard;
