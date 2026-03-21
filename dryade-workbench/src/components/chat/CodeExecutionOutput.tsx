// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Loader2, Check, X, AlertTriangle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { CodeExecuteResponse, CodeExecutionStatus } from "@/types/extended-api";

export interface CodeExecutionOutputProps {
  status: CodeExecutionStatus;
  result: CodeExecuteResponse | null;
  error: string | null;
  className?: string;
}

/** Detect if text looks like tab-separated or comma-separated tabular data. */
function detectTable(text: string): { rows: string[][]; separator: string } | null {
  const lines = text.trim().split("\n");
  if (lines.length < 3) return null;

  // Try tab-separated first
  const tabCols = lines.map((l) => l.split("\t"));
  const tabColCount = tabCols[0].length;
  if (tabColCount >= 2 && tabCols.every((r) => r.length === tabColCount)) {
    return { rows: tabCols, separator: "tab" };
  }

  // Try comma-separated
  const csvCols = lines.map((l) => l.split(","));
  const csvColCount = csvCols[0].length;
  if (csvColCount >= 2 && csvCols.every((r) => r.length === csvColCount)) {
    return { rows: csvCols, separator: "csv" };
  }

  return null;
}

export function CodeExecutionOutput({
  status,
  result,
  error,
  className,
}: CodeExecutionOutputProps) {
  const { t } = useTranslation("chat");

  const tableData = useMemo(() => {
    if (!result?.stdout) return null;
    return detectTable(result.stdout);
  }, [result?.stdout]);

  return (
    <div
      className={cn(
        "mt-1 rounded-md border border-border bg-background/60 text-xs overflow-hidden",
        className,
      )}
    >
      {/* Status bar */}
      <div className="flex items-center gap-2 px-3 py-1.5 bg-muted/30 border-b border-border">
        {status === "running" && (
          <>
            <Loader2 size={12} className="animate-spin text-primary" />
            <span className="text-muted-foreground">
              {t("codeExecution.running")}
            </span>
          </>
        )}

        {status === "complete" && result && result.exit_code === 0 && (
          <>
            <Check size={12} className="text-green-500" />
            <span className="text-green-600 dark:text-green-400">
              {t("codeExecution.complete")}
            </span>
            <Badge variant="outline" className="ml-auto text-[10px] h-5">
              {t("codeExecution.executionTime", {
                time: result.execution_time_ms.toFixed(0),
              })}
            </Badge>
          </>
        )}

        {status === "complete" && result && result.exit_code !== 0 && (
          <>
            <AlertTriangle size={12} className="text-yellow-500" />
            <span className="text-yellow-600 dark:text-yellow-400">
              {t("codeExecution.exitCode", { code: result.exit_code })}
            </span>
            <Badge variant="outline" className="ml-auto text-[10px] h-5">
              {t("codeExecution.executionTime", {
                time: result.execution_time_ms.toFixed(0),
              })}
            </Badge>
          </>
        )}

        {status === "error" && (
          <>
            <X size={12} className="text-destructive" />
            <span className="text-destructive">
              {error || t("codeExecution.error")}
            </span>
          </>
        )}
      </div>

      {/* stdout */}
      {result?.stdout ? (
        <div>
          <div className="px-3 py-1 text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
            {t("codeExecution.stdout")}
          </div>
          {tableData ? (
            <div className="overflow-x-auto px-3 pb-2">
              <table className="min-w-full text-sm border-collapse border border-border">
                <thead>
                  <tr>
                    {tableData.rows[0].map((cell, i) => (
                      <th
                        key={i}
                        className="border border-border bg-muted/50 px-3 py-1.5 text-left font-medium"
                      >
                        {cell.trim()}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {tableData.rows.slice(1).map((row, ri) => (
                    <tr key={ri}>
                      {row.map((cell, ci) => (
                        <td key={ci} className="border border-border px-3 py-1.5">
                          {cell.trim()}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <pre className="px-3 pb-2 font-mono text-xs whitespace-pre-wrap max-h-64 overflow-auto">
              {result.stdout}
            </pre>
          )}
        </div>
      ) : (
        status === "complete" &&
        result &&
        !result.stderr && (
          <div className="px-3 py-2 text-muted-foreground italic">
            {t("codeExecution.noOutput")}
          </div>
        )
      )}

      {/* stderr */}
      {result?.stderr && (
        <div>
          <div className="px-3 py-1 text-[10px] font-medium text-destructive uppercase tracking-wide">
            {t("codeExecution.stderr")}
          </div>
          <pre className="px-3 pb-2 font-mono text-xs text-destructive whitespace-pre-wrap max-h-64 overflow-auto">
            {result.stderr}
          </pre>
        </div>
      )}

      {/* Footer with execution time */}
      {result && status === "complete" && (
        <div className="px-3 py-1 border-t border-border text-[10px] text-muted-foreground">
          {t("codeExecution.executionTime", {
            time: result.execution_time_ms.toFixed(0),
          })}
        </div>
      )}
    </div>
  );
}
