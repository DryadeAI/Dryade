// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { cn } from "@/lib/utils";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Star, Check, X } from "lucide-react";
import type { Model } from "@/types/extended-api";

interface ModelComparisonTableProps {
  models: Model[];
  className?: string;
}

const ModelComparisonTable = ({ models, className }: ModelComparisonTableProps) => {
  if (models.length === 0) {
    return (
      <div className={cn("text-center py-8 text-muted-foreground", className)}>
        Select models to compare
      </div>
    );
  }

  const metrics = [
    { key: "latency_avg_ms", label: "Avg Latency", unit: "ms", lowerBetter: true },
    { key: "tokens_per_second", label: "Tokens/sec", unit: "", lowerBetter: false },
    { key: "success_rate", label: "Success Rate", unit: "%", lowerBetter: false },
    { key: "total_requests", label: "Total Requests", unit: "", lowerBetter: false },
    { key: "cost_per_1k_tokens", label: "Cost/1k tokens", unit: "$", lowerBetter: true },
  ];

  const getBestValue = (key: string, lowerBetter: boolean) => {
    const values = models
      .map((m) => m.metrics?.[key as keyof typeof m.metrics])
      .filter((v) => v !== undefined) as number[];
    if (values.length === 0) return null;
    return lowerBetter ? Math.min(...values) : Math.max(...values);
  };

  return (
    <div className={cn("rounded-lg border border-border overflow-hidden", className)}>
      <Table>
        <TableHeader>
          <TableRow className="bg-muted/30">
            <TableHead className="w-40">Metric</TableHead>
            {models.map((model) => (
              <TableHead key={model.id} className="text-center">
                <div className="flex items-center justify-center gap-1">
                  <span>{model.display_name}</span>
                  {model.is_default && (
                    <Star className="w-3 h-3 text-warning fill-warning" />
                  )}
                </div>
                <div className="text-xs font-normal text-muted-foreground">
                  {model.provider}
                </div>
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {/* Status row */}
          <TableRow>
            <TableCell className="font-medium">Status</TableCell>
            {models.map((model) => (
              <TableCell key={model.id} className="text-center">
                <Badge
                  variant="outline"
                  className={cn(
                    model.status === "available" && "text-success border-success/30",
                    model.status === "loading" && "text-warning border-warning/30",
                    model.status === "error" && "text-destructive border-destructive/30",
                    model.status === "deprecated" && "text-muted-foreground"
                  )}
                >
                  {model.status}
                </Badge>
              </TableCell>
            ))}
          </TableRow>

          {/* Custom model row */}
          <TableRow>
            <TableCell className="font-medium">Custom Model</TableCell>
            {models.map((model) => (
              <TableCell key={model.id} className="text-center">
                {model.is_custom ? (
                  <Check className="w-4 h-4 text-success mx-auto" />
                ) : (
                  <X className="w-4 h-4 text-muted-foreground mx-auto" />
                )}
              </TableCell>
            ))}
          </TableRow>

          {/* Metric rows */}
          {metrics.map((metric) => {
            const bestValue = getBestValue(metric.key, metric.lowerBetter);

            return (
              <TableRow key={metric.key}>
                <TableCell className="font-medium">{metric.label}</TableCell>
                {models.map((model) => {
                  const value = model.metrics?.[metric.key as keyof typeof model.metrics];
                  const isBest = value !== undefined && value === bestValue;

                  return (
                    <TableCell
                      key={model.id}
                      className={cn(
                        "text-center font-mono",
                        isBest && "text-success font-semibold"
                      )}
                    >
                      {value !== undefined ? (
                        <>
                          {metric.unit === "$" && "$"}
                          {typeof value === "number" ? value.toLocaleString() : value}
                          {metric.unit && metric.unit !== "$" && metric.unit}
                        </>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                  );
                })}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
};

export default ModelComparisonTable;
