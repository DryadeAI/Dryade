// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// FactoryPage - Artifact listing and management for factory-created agents, tools, and skills
// Follows AgentsPage pattern with card grid, filtering, search, empty states, and detail panel

import { useState, useEffect, useMemo, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { Plus, Search, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import ArtifactCard from "@/components/factory/ArtifactCard";
import ArtifactStatusBadge from "@/components/factory/ArtifactStatusBadge";
import CreateArtifactDialog from "@/components/factory/CreateArtifactDialog";
import { statusConfig } from "@/components/factory/ArtifactStatusBadge";
import EmptyState from "@/components/shared/EmptyState";
import { factoryApi } from "@/services/api";
import type { FactoryArtifact, ArtifactType, ArtifactStatus } from "@/services/api/factory";

type TypeFilter = "all" | ArtifactType;
type StatusFilter = "all" | ArtifactStatus;

const typeFilterKeys: TypeFilter[] = ["all", "agent", "tool", "skill"];

const statusFilterEntries = Object.entries(statusConfig).map(([key, cfg]) => ({
  value: key as ArtifactStatus,
  label: cfg.label,
}));

const FactoryPage = () => {
  const { t } = useTranslation('factory');
  const [artifacts, setArtifacts] = useState<FactoryArtifact[]>([]);
  const [loading, setLoading] = useState(true);
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [selectedArtifact, setSelectedArtifact] = useState<FactoryArtifact | null>(null);

  const loadArtifacts = useCallback(async () => {
    setLoading(true);
    try {
      const { items } = await factoryApi.list();
      setArtifacts(items);
    } catch (error) {
      console.error("Failed to load factory artifacts:", error);
      toast.error(t("toast.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    loadArtifacts();
  }, [loadArtifacts]);

  const filteredArtifacts = useMemo(() => {
    let result = [...artifacts];

    // Sort by most recently updated first
    result.sort(
      (a, b) =>
        new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
    );

    if (typeFilter !== "all") {
      result = result.filter((a) => a.artifact_type === typeFilter);
    }

    if (statusFilter !== "all") {
      result = result.filter((a) => a.status === statusFilter);
    }

    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      result = result.filter(
        (a) =>
          a.name.toLowerCase().includes(query) ||
          a.source_prompt.toLowerCase().includes(query)
      );
    }

    return result;
  }, [artifacts, typeFilter, statusFilter, searchQuery]);

  const handleDelete = useCallback(
    async (name: string) => {
      try {
        await factoryApi.delete(name);
        toast.success(t("toast.deleted", { name }));
        // Close detail panel if the deleted artifact was selected
        if (selectedArtifact?.name === name) {
          setSelectedArtifact(null);
        }
        loadArtifacts();
      } catch (error) {
        console.error("Failed to delete artifact:", error);
        toast.error(t("toast.deleteFailed"));
      }
    },
    [loadArtifacts, selectedArtifact, t]
  );

  const handleUpdate = useCallback(
    async (artifact: FactoryArtifact) => {
      try {
        await factoryApi.update(artifact.name, {
          goal: artifact.source_prompt,
        });
        toast.success(t("toast.updated", { name: artifact.name }));
        loadArtifacts();
      } catch (error) {
        console.error("Failed to update artifact:", error);
        toast.error(t("toast.updateFailed"));
      }
    },
    [loadArtifacts, t]
  );

  const handleRollback = useCallback(
    async (artifact: FactoryArtifact) => {
      try {
        const targetVersion = artifact.version - 1;
        await factoryApi.rollback(artifact.name, targetVersion);
        toast.success(
          t("toast.rolledBack", { name: artifact.name, version: targetVersion })
        );
        // Refresh detail panel data
        if (selectedArtifact?.name === artifact.name) {
          setSelectedArtifact(null);
        }
        loadArtifacts();
      } catch (error) {
        console.error("Failed to rollback artifact:", error);
        toast.error(t("toast.rollbackFailed"));
      }
    },
    [loadArtifacts, selectedArtifact, t]
  );

  const handleApprove = useCallback(
    async (artifact: FactoryArtifact) => {
      try {
        toast.info(`Approving ${artifact.name}...`);
        const result = await factoryApi.approve(artifact.name);
        if (result.success) {
          toast.success(t("toast.updated", { name: artifact.name }));
        } else {
          toast.error(result.message || "Approval failed");
        }
        loadArtifacts();
      } catch (error) {
        console.error("Failed to approve artifact:", error);
        toast.error("Failed to approve artifact");
      }
    },
    [loadArtifacts, t]
  );

  const handleClearFilters = () => {
    setTypeFilter("all");
    setStatusFilter("all");
    setSearchQuery("");
  };

  const hasActiveFilters =
    typeFilter !== "all" || statusFilter !== "all" || searchQuery !== "";

  return (
    <div className="flex h-full flex-col" data-testid="factory-container">
      {/* Header */}
      <header className="shrink-0 p-6 border-b border-border">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-2xl font-bold text-foreground">{t("title")}</h1>
            <p className="text-sm text-muted-foreground">
              {t("subtitle")}
            </p>
          </div>
          <Button onClick={() => setCreateDialogOpen(true)}>
            <Plus className="w-4 h-4 mr-2" aria-hidden="true" />
            {t("createArtifact")}
          </Button>
        </div>

        {/* Search + Filters */}
        <div className="flex items-center gap-3">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" aria-hidden="true" />
            <Input
              placeholder={t("searchPlaceholder")}
              aria-label="Search artifacts"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>

          {/* Type filter tabs */}
          <div className="flex items-center gap-1 rounded-lg border border-border p-1">
            {typeFilterKeys.map((key) => (
              <Button
                key={key}
                variant={typeFilter === key ? "default" : "ghost"}
                size="sm"
                className="h-7 px-3 text-xs"
                onClick={() => setTypeFilter(key)}
              >
                {t(`typeFilter.${key}`)}
              </Button>
            ))}
          </div>

          {/* Status filter dropdown */}
          <Select
            value={statusFilter}
            onValueChange={(v) => setStatusFilter(v as StatusFilter)}
          >
            <SelectTrigger className="w-[160px]">
              <SelectValue placeholder={t("statusFilter.allStatuses")} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t("statusFilter.allStatuses")}</SelectItem>
              {statusFilterEntries.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </header>

      {/* Grid */}
      <div className="flex-1 overflow-auto p-6">
        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="glass-card p-4 space-y-3">
                <div className="flex items-start justify-between">
                  <Skeleton className="h-5 w-32" />
                  <Skeleton className="h-5 w-20" />
                </div>
                <div className="flex gap-2">
                  <Skeleton className="h-5 w-14" />
                  <Skeleton className="h-5 w-16" />
                </div>
                <Skeleton className="h-8 w-full" />
                <div className="flex items-center justify-between pt-2 border-t border-border">
                  <Skeleton className="h-4 w-10" />
                  <Skeleton className="h-4 w-24" />
                </div>
              </div>
            ))}
          </div>
        ) : filteredArtifacts.length === 0 ? (
          artifacts.length === 0 ? (
            <EmptyState
              variant="default"
              title={t("emptyState.title")}
              description={t("emptyState.description")}
              className="h-full"
              size="lg"
            />
          ) : (
            <EmptyState
              variant="search"
              title={t("emptyState.noMatchTitle")}
              description={t("emptyState.noMatchDescription")}
              action={{
                label: t("emptyState.clearFilters"),
                onClick: handleClearFilters,
              }}
              className="h-full"
            />
          )
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredArtifacts.map((artifact) => (
              <ArtifactCard
                key={artifact.id}
                artifact={artifact}
                onDelete={() => handleDelete(artifact.name)}
                onUpdate={(a) => handleUpdate(a)}
                onRollback={(a) => handleRollback(a)}
                onApprove={(a) => handleApprove(a)}
                onSelect={(a) => setSelectedArtifact(a)}
              />
            ))}
          </div>
        )}
      </div>

      <CreateArtifactDialog
        open={createDialogOpen}
        onOpenChange={setCreateDialogOpen}
        onCreated={loadArtifacts}
      />

      {/* Artifact Detail Dialog */}
      <Dialog
        open={selectedArtifact !== null}
        onOpenChange={(open) => {
          if (!open) setSelectedArtifact(null);
        }}
      >
        <DialogContent className="glass-card sm:max-w-2xl max-h-[85vh] overflow-y-auto">
          {selectedArtifact && (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2">
                  {selectedArtifact.name}
                  <ArtifactStatusBadge status={selectedArtifact.status} />
                </DialogTitle>
                <DialogDescription>
                  {selectedArtifact.source_prompt}
                </DialogDescription>
              </DialogHeader>

              <div className="mt-4 space-y-6">
                {/* Metadata grid */}
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <p className="text-muted-foreground text-xs mb-1">{t("detail.type")}</p>
                    <Badge variant="outline">
                      {t(`typeFilter.${selectedArtifact.artifact_type}`)}
                    </Badge>
                  </div>
                  <div>
                    <p className="text-muted-foreground text-xs mb-1">{t("detail.framework")}</p>
                    <Badge variant="outline">{selectedArtifact.framework}</Badge>
                  </div>
                  <div>
                    <p className="text-muted-foreground text-xs mb-1">{t("detail.version")}</p>
                    <span className="font-medium">v{selectedArtifact.version}</span>
                  </div>
                  <div>
                    <p className="text-muted-foreground text-xs mb-1">{t("detail.trigger")}</p>
                    <span className="font-medium">{selectedArtifact.trigger || t("detail.triggerManual")}</span>
                  </div>
                  <div>
                    <p className="text-muted-foreground text-xs mb-1">{t("detail.created")}</p>
                    <span className="text-foreground">
                      {new Date(selectedArtifact.created_at).toLocaleString()}
                    </span>
                  </div>
                  <div>
                    <p className="text-muted-foreground text-xs mb-1">{t("detail.updated")}</p>
                    <span className="text-foreground">
                      {new Date(selectedArtifact.updated_at).toLocaleString()}
                    </span>
                  </div>
                </div>

                {/* Test results */}
                {selectedArtifact.test_result && (
                  <div>
                    <h4 className="text-sm font-medium text-foreground mb-2">
                      {t("detail.testResults")}
                    </h4>
                    <div className="flex items-center gap-2 mb-2">
                      <Badge
                        variant={selectedArtifact.test_passed ? "default" : "destructive"}
                        className="text-xs"
                      >
                        {selectedArtifact.test_passed ? t("detail.testPassed") : t("detail.testFailed")}
                      </Badge>
                      <span className="text-xs text-muted-foreground">
                        {selectedArtifact.test_iterations !== 1
                          ? t("detail.iterations", { count: selectedArtifact.test_iterations })
                          : t("detail.iteration", { count: selectedArtifact.test_iterations })}
                      </span>
                    </div>
                    <pre className="text-xs bg-muted/50 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap max-h-48">
                      {selectedArtifact.test_result}
                    </pre>
                  </div>
                )}

                {/* Configuration JSON */}
                {selectedArtifact.config_json &&
                  Object.keys(selectedArtifact.config_json).length > 0 && (
                    <div>
                      <h4 className="text-sm font-medium text-foreground mb-2">
                        {t("detail.configuration")}
                      </h4>
                      <pre className="text-xs bg-muted/50 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap max-h-64">
                        {JSON.stringify(selectedArtifact.config_json, null, 2)}
                      </pre>
                    </div>
                  )}

                {/* Artifact path */}
                {selectedArtifact.artifact_path && (
                  <div>
                    <h4 className="text-sm font-medium text-foreground mb-2">
                      {t("detail.artifactPath")}
                    </h4>
                    <code className="text-xs bg-muted/50 rounded px-2 py-1 break-all">
                      {selectedArtifact.artifact_path}
                    </code>
                  </div>
                )}

                {/* Tags */}
                {selectedArtifact.tags && selectedArtifact.tags.length > 0 && (
                  <div>
                    <h4 className="text-sm font-medium text-foreground mb-2">
                      {t("detail.tags")}
                    </h4>
                    <div className="flex flex-wrap gap-1">
                      {selectedArtifact.tags.map((tag) => (
                        <Badge key={tag} variant="secondary" className="text-xs">
                          {tag}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default FactoryPage;
