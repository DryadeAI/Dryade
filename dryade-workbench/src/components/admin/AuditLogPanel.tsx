// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Card, CardContent } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { ChevronLeft, ChevronRight, Download, AlertTriangle, ChevronDown, FileJson } from "lucide-react";
import { toast } from "sonner";
import { adminApi } from "@/services/api/admin";
import type { CoreAuditEntry } from "@/types/admin";
import AuditChainVerifier from "./AuditChainVerifier";

const RESOURCE_TYPES = ["conversation", "workflow", "project", "knowledge", "agent", "user"];
const SEVERITIES = ["info", "warning", "error", "critical"];
const PER_PAGE_OPTIONS = [25, 50, 100, 200];

export default function AuditLogPanel() {
  const { t } = useTranslation("admin");
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(25);
  const [filters, setFilters] = useState({
    user_id: "",
    action: "",
    resource_type: "",
    severity: "",
    date_from: "",
    date_to: "",
  });
  const [expandedRow, setExpandedRow] = useState<number | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ["admin", "audit", page, perPage, filters],
    queryFn: () =>
      adminApi.queryCoreAudit({
        page,
        per_page: perPage,
        user_id: filters.user_id || undefined,
        action: filters.action || undefined,
        resource_type: filters.resource_type || undefined,
        severity: filters.severity || undefined,
        date_from: filters.date_from || undefined,
        date_to: filters.date_to || undefined,
      }),
  });

  const totalPages = data?.pages ?? 0;

  const clearFilters = () => {
    setFilters({ user_id: "", action: "", resource_type: "", severity: "", date_from: "", date_to: "" });
    setPage(1);
  };

  const handleExport = useCallback(async () => {
    try {
      const blob = await adminApi.exportAuditLogs({
        date_from: filters.date_from || undefined,
        date_to: filters.date_to || undefined,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `audit-export-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success(t("auditLog.exportSuccess"));
    } catch {
      toast.error(t("auditLog.exportError"));
    }
  }, [filters.date_from, filters.date_to, t]);

  const severityBadge = (severity: string) => {
    const variants: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
      info: "secondary",
      warning: "outline",
      error: "destructive",
      critical: "destructive",
    };
    return (
      <Badge variant={variants[severity] ?? "secondary"} className={severity === "critical" ? "font-bold" : ""}>
        {t(`auditLog.${severity}`, severity)}
      </Badge>
    );
  };

  const formatTimestamp = (ts: string) => {
    try {
      return new Date(ts).toLocaleString();
    } catch {
      return ts;
    }
  };

  if (error) {
    return (
      <Card className="border-destructive/50">
        <CardContent className="flex items-center gap-3 py-6">
          <AlertTriangle className="h-5 w-5 text-destructive" />
          <span className="text-sm text-destructive">{t("common.error")}</span>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold">{t("auditLog.title")}</h2>
          <p className="text-sm text-muted-foreground mt-1">{t("auditLog.description")}</p>
        </div>
        <Button variant="outline" size="sm" onClick={handleExport}>
          <Download className="h-4 w-4 mr-1" />
          {t("auditLog.export")}
        </Button>
      </div>

      {/* Chain Verifier */}
      <AuditChainVerifier />

      {/* Filters */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
        <Input
          placeholder={t("auditLog.userId")}
          value={filters.user_id}
          onChange={(e) => { setFilters((f) => ({ ...f, user_id: e.target.value })); setPage(1); }}
          className="h-9 text-sm"
        />
        <Input
          placeholder={t("auditLog.action")}
          value={filters.action}
          onChange={(e) => { setFilters((f) => ({ ...f, action: e.target.value })); setPage(1); }}
          className="h-9 text-sm"
        />
        <Select
          value={filters.resource_type || "all"}
          onValueChange={(v) => { setFilters((f) => ({ ...f, resource_type: v === "all" ? "" : v })); setPage(1); }}
        >
          <SelectTrigger className="h-9 text-sm">
            <SelectValue placeholder={t("auditLog.resourceType")} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t("auditLog.allResources")}</SelectItem>
            {RESOURCE_TYPES.map((rt) => (
              <SelectItem key={rt} value={rt}>{rt}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={filters.severity || "all"}
          onValueChange={(v) => { setFilters((f) => ({ ...f, severity: v === "all" ? "" : v })); setPage(1); }}
        >
          <SelectTrigger className="h-9 text-sm">
            <SelectValue placeholder={t("auditLog.severity")} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t("auditLog.allSeverities")}</SelectItem>
            {SEVERITIES.map((s) => (
              <SelectItem key={s} value={s}>{t(`auditLog.${s}`, s)}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Input
          type="date"
          placeholder={t("auditLog.dateFrom")}
          value={filters.date_from}
          onChange={(e) => { setFilters((f) => ({ ...f, date_from: e.target.value })); setPage(1); }}
          className="h-9 text-sm"
        />
        <Input
          type="date"
          placeholder={t("auditLog.dateTo")}
          value={filters.date_to}
          onChange={(e) => { setFilters((f) => ({ ...f, date_to: e.target.value })); setPage(1); }}
          className="h-9 text-sm"
        />
      </div>

      {Object.values(filters).some(Boolean) && (
        <Button variant="ghost" size="sm" onClick={clearFilters}>
          {t("auditLog.clearFilters")}
        </Button>
      )}

      {/* Results Table */}
      <div className="border rounded-md">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-8" />
              <TableHead>{t("auditLog.timestamp")}</TableHead>
              <TableHead>{t("auditLog.user")}</TableHead>
              <TableHead>{t("auditLog.action")}</TableHead>
              <TableHead>{t("auditLog.resourceType")}</TableHead>
              <TableHead>{t("auditLog.severity")}</TableHead>
              <TableHead>{t("auditLog.ipAddress")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <TableRow key={i}>
                  {Array.from({ length: 7 }).map((_, j) => (
                    <TableCell key={j}><Skeleton className="h-4 w-20" /></TableCell>
                  ))}
                </TableRow>
              ))
            ) : data?.items?.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="text-center py-8 text-muted-foreground">
                  <FileJson className="h-8 w-8 mx-auto mb-2 opacity-30" />
                  {t("auditLog.noEntries")}
                </TableCell>
              </TableRow>
            ) : (
              data?.items?.map((entry: CoreAuditEntry) => (
                <Collapsible key={entry.id} asChild open={expandedRow === entry.id} onOpenChange={(open) => setExpandedRow(open ? entry.id : null)}>
                  <>
                    <TableRow className="cursor-pointer hover:bg-muted/50">
                      <TableCell>
                        <CollapsibleTrigger asChild>
                          <Button variant="ghost" size="sm" className="h-6 w-6 p-0">
                            <ChevronDown className={`h-3 w-3 transition-transform ${expandedRow === entry.id ? "" : "-rotate-90"}`} />
                          </Button>
                        </CollapsibleTrigger>
                      </TableCell>
                      <TableCell className="text-xs font-mono">{formatTimestamp(entry.created_at)}</TableCell>
                      <TableCell className="text-xs truncate max-w-[120px]">{entry.user_id}</TableCell>
                      <TableCell><Badge variant="outline" className="text-xs">{entry.action}</Badge></TableCell>
                      <TableCell className="text-xs">{entry.resource_type}</TableCell>
                      <TableCell>{severityBadge(entry.event_severity)}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{entry.ip_address}</TableCell>
                    </TableRow>
                    <CollapsibleContent asChild>
                      <TableRow>
                        <TableCell colSpan={7} className="bg-muted/20 p-4">
                          <div className="text-xs space-y-1">
                            <p><strong>ID:</strong> {entry.id}</p>
                            <p><strong>Resource ID:</strong> {entry.resource_id}</p>
                            <p><strong>Entry Hash:</strong> <span className="font-mono">{entry.entry_hash}</span></p>
                            {entry.metadata && (
                              <details>
                                <summary className="cursor-pointer text-primary">Metadata</summary>
                                <pre className="mt-1 p-2 bg-muted rounded text-[10px] overflow-auto max-h-32">
                                  {JSON.stringify(entry.metadata, null, 2)}
                                </pre>
                              </details>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    </CollapsibleContent>
                  </>
                </Collapsible>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Select value={String(perPage)} onValueChange={(v) => { setPerPage(Number(v)); setPage(1); }}>
            <SelectTrigger className="w-20 h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PER_PAGE_OPTIONS.map((n) => (
                <SelectItem key={n} value={String(n)}>{n}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <span className="text-xs text-muted-foreground">{t("auditLog.perPage")}</span>
        </div>

        {totalPages > 1 && (
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">
              {page} / {totalPages}
            </span>
            <Button variant="outline" size="sm" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}>
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button variant="outline" size="sm" onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page >= totalPages}>
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
