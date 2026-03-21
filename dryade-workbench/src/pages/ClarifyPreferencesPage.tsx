// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
/**
 * ClarifyPreferencesPage - Native workbench page for managing clarification preferences.
 *
 * Converted from plugin iframe to native page (Phase 191).
 * This is a free-core feature available to all users including community.
 * Uses workbench shadcn/ui components directly (no SDK bridge, no iframe).
 *
 * The clarify feature works through the chat flow: when the AI needs clarification,
 * it presents a form. User answers are saved as preferences that prefill future forms.
 * This page lets users manage those saved preferences.
 *
 * API endpoints: /api/clarify/preferences
 */

import { useState, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import EmptyState from "@/components/shared/EmptyState";
import { fetchWithAuth } from "@/services/apiClient";
import {
  HelpCircle,
  Trash2,
  RefreshCw,
  Globe,
  FolderOpen,
  Loader2,
} from "lucide-react";
import { toast } from "sonner";

// ── Types ─────────────────────────────────────────────────────

interface Preference {
  id: number;
  question: string;
  answer: unknown;
  answer_type: string;
  project_id: string | null;
  used_count: number;
  match_threshold: number;
  created_at?: string;
  updated_at?: string;
}

// ── API helpers ───────────────────────────────────────────────

async function fetchPreferences(includeGlobal = true): Promise<Preference[]> {
  const qs = new URLSearchParams({ include_global: String(includeGlobal) });
  return fetchWithAuth<Preference[]>(`/clarify/preferences?${qs}`);
}

async function deletePreference(id: number): Promise<void> {
  await fetchWithAuth(`/clarify/preferences/${id}`, { method: "DELETE" });
}

async function updatePreference(
  id: number,
  data: { match_threshold?: number; answer?: unknown },
): Promise<Preference> {
  return fetchWithAuth<Preference>(`/clarify/preferences/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

// ── Main Page Component ───────────────────────────────────────

const ClarifyPreferencesPage = () => {
  const { t } = useTranslation();
  const [preferences, setPreferences] = useState<Preference[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showGlobal, setShowGlobal] = useState(true);
  const [search, setSearch] = useState("");
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);

  const loadPreferences = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const prefs = await fetchPreferences(showGlobal);
      setPreferences(prefs);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load preferences");
    } finally {
      setLoading(false);
    }
  }, [showGlobal]);

  useEffect(() => {
    void loadPreferences();
  }, [loadPreferences]);

  const handleDelete = async (id: number) => {
    setDeletingId(id);
    try {
      await deletePreference(id);
      setPreferences((prev) => prev.filter((p) => p.id !== id));
      toast.success("Preference deleted");
    } catch {
      toast.error("Failed to delete preference");
    } finally {
      setDeletingId(null);
      setConfirmDeleteId(null);
    }
  };

  const handleUpdateThreshold = async (id: number, threshold: number) => {
    try {
      const updated = await updatePreference(id, { match_threshold: threshold });
      setPreferences((prev) => prev.map((p) => (p.id === id ? updated : p)));
    } catch {
      toast.error("Failed to update threshold");
    }
  };

  const filteredPreferences = preferences.filter((p) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      p.question.toLowerCase().includes(q) ||
      String(p.answer).toLowerCase().includes(q)
    );
  });

  return (
    <div className="p-6 space-y-6 h-full overflow-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-foreground flex items-center gap-2">
            <HelpCircle className="w-6 h-6" aria-hidden="true" />
            {t("clarify.title", "Clarification Preferences")}
          </h1>
          <p className="text-muted-foreground">
            {t("clarify.subtitle", "Manage saved answers for clarification questions. These prefill forms automatically.")}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Switch
              id="show-global"
              checked={showGlobal}
              onCheckedChange={setShowGlobal}
            />
            <Label htmlFor="show-global" className="text-sm">
              Include global
            </Label>
          </div>
          <Button variant="outline" onClick={() => void loadPreferences()} disabled={loading}>
            {loading ? (
              <Loader2 className="w-4 h-4 mr-1 motion-safe:animate-spin" aria-hidden="true" />
            ) : (
              <RefreshCw className="w-4 h-4 mr-1" aria-hidden="true" />
            )}
            Refresh
          </Button>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-lg bg-destructive/10 text-destructive text-sm">{error}</div>
      )}

      {/* Search */}
      <div className="flex items-center gap-3">
        <Input
          placeholder="Search preferences..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-sm"
        />
        <span className="text-sm text-muted-foreground">
          {filteredPreferences.length} preference{filteredPreferences.length !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Stats */}
      {!loading && preferences.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Card className="bg-card/60 backdrop-blur-md">
            <CardContent className="p-4 flex items-center gap-3">
              <div className="p-2 rounded-lg bg-primary/10">
                <HelpCircle className="w-5 h-5 text-primary" aria-hidden="true" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Total Preferences</p>
                <p className="text-xl font-bold">{preferences.length}</p>
              </div>
            </CardContent>
          </Card>
          <Card className="bg-card/60 backdrop-blur-md">
            <CardContent className="p-4 flex items-center gap-3">
              <div className="p-2 rounded-lg bg-primary/10">
                <Globe className="w-5 h-5 text-primary" aria-hidden="true" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Global</p>
                <p className="text-xl font-bold">{preferences.filter((p) => !p.project_id).length}</p>
              </div>
            </CardContent>
          </Card>
          <Card className="bg-card/60 backdrop-blur-md">
            <CardContent className="p-4 flex items-center gap-3">
              <div className="p-2 rounded-lg bg-primary/10">
                <FolderOpen className="w-5 h-5 text-primary" aria-hidden="true" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Project-specific</p>
                <p className="text-xl font-bold">{preferences.filter((p) => !!p.project_id).length}</p>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Preferences List */}
      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Card key={i}>
              <CardContent className="p-4">
                <Skeleton className="h-5 w-3/4 mb-2" />
                <Skeleton className="h-4 w-1/2" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : filteredPreferences.length === 0 ? (
        <EmptyState
          icon={<HelpCircle className="w-8 h-8 text-muted-foreground" />}
          title={search ? "No matching preferences" : "No saved preferences yet"}
          description={
            search
              ? "Try a different search term."
              : "Answer clarification forms during conversations and your choices will be saved here."
          }
        />
      ) : (
        <div className="space-y-3">
          {filteredPreferences.map((pref) => (
            <Card
              key={pref.id}
              className="bg-card/60 backdrop-blur-md hover:border-border motion-safe:transition-colors"
            >
              <CardContent className="p-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-foreground mb-2">{pref.question}</p>
                    <div className="flex items-center gap-3 flex-wrap text-sm">
                      <span className="text-muted-foreground">
                        Answer:{" "}
                        <code className="bg-muted px-1.5 py-0.5 rounded text-xs font-mono">
                          {JSON.stringify(pref.answer)}
                        </code>
                      </span>
                      <Badge variant="outline">{pref.answer_type}</Badge>
                      <span className="text-muted-foreground">
                        Used: {pref.used_count}x
                      </span>
                      {pref.project_id ? (
                        <Badge className="bg-info/10 text-info border-info/30">Project</Badge>
                      ) : (
                        <Badge variant="secondary">Global</Badge>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-3 shrink-0">
                    <div className="flex items-center gap-1.5">
                      <Label className="text-xs text-muted-foreground whitespace-nowrap">Threshold:</Label>
                      <Input
                        type="number"
                        min={0.5}
                        max={1.0}
                        step={0.05}
                        value={pref.match_threshold}
                        onChange={(e) => void handleUpdateThreshold(pref.id, parseFloat(e.target.value))}
                        className="w-20 h-7 text-xs"
                      />
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-muted-foreground hover:text-destructive"
                      onClick={() => setConfirmDeleteId(pref.id)}
                      disabled={deletingId === pref.id}
                    >
                      {deletingId === pref.id ? (
                        <Loader2 className="w-4 h-4 motion-safe:animate-spin" />
                      ) : (
                        <Trash2 className="w-4 h-4" />
                      )}
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Delete Confirmation Dialog */}
      <Dialog open={confirmDeleteId !== null} onOpenChange={() => setConfirmDeleteId(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Preference</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete this preference? You will need to answer similar
              clarification questions again.
            </DialogDescription>
          </DialogHeader>
          <div className="flex justify-end gap-2 mt-4">
            <Button variant="outline" onClick={() => setConfirmDeleteId(null)}>Cancel</Button>
            <Button
              variant="destructive"
              onClick={() => confirmDeleteId !== null && void handleDelete(confirmDeleteId)}
              disabled={deletingId !== null}
            >
              {deletingId !== null ? (
                <Loader2 className="w-4 h-4 mr-1 motion-safe:animate-spin" />
              ) : (
                <Trash2 className="w-4 h-4 mr-1" />
              )}
              Delete
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default ClarifyPreferencesPage;
