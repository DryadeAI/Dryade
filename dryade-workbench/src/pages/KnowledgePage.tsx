// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Slider } from "@/components/ui/slider";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import DocumentCard from "@/components/knowledge/DocumentCard";
import ChunkViewer from "@/components/knowledge/ChunkViewer";
import BindingPanel from "@/components/knowledge/BindingPanel";
import EmptyState from "@/components/shared/EmptyState";
import { knowledgeApi, agentsApi, advancedKnowledgeApi } from "@/services/api";
import { BookOpen, Upload, Search, FileText, File, X, Loader2 } from "lucide-react";
import { toast } from "sonner";
import type { KnowledgeSource, SearchResult, UploadProgress } from "@/types/extended-api";

const KnowledgePage = () => {
  const { t } = useTranslation('knowledge');
  const [sources, setSources] = useState<KnowledgeSource[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [threshold, setThreshold] = useState([0.3]);
  const [totalResults, setTotalResults] = useState<number>(0);
  const [searchOffset, setSearchOffset] = useState(0);
  const [uploadProgress, setUploadProgress] = useState<UploadProgress | null>(null);
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);
  const selectedSource = sources.find(s => s.id === selectedSourceId) || null;
  const setSelectedSource = (source: KnowledgeSource | null) => setSelectedSourceId(source?.id || null);
  const [showBindingPanel, setShowBindingPanel] = useState(false);
  const [selectedChunk, setSelectedChunk] = useState<SearchResult | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [activeTab, setActiveTab] = useState("sources");
  const [availableAgents, setAvailableAgents] = useState<Array<{ id: string; name: string; framework: string }>>([]);

  // Advanced RAG test panel state
  const [advancedAvailable, setAdvancedAvailable] = useState(false);
  const [advancedQuery, setAdvancedQuery] = useState("");
  const [advancedResults, setAdvancedResults] = useState<SearchResult[]>([]);
  const [advancedVariants, setAdvancedVariants] = useState<string[]>([]);
  const [advancedStrategies, setAdvancedStrategies] = useState<string[]>([]);
  const [isAdvancedSearching, setIsAdvancedSearching] = useState(false);
  const [multiQueryEnabled, setMultiQueryEnabled] = useState(true);
  const [hydeEnabled, setHydeEnabled] = useState(true);
  const [rerankEnabled, setRerankEnabled] = useState(true);

  // Load agents for BindingPanel
  useEffect(() => {
    agentsApi.getAgents().then(({ agents }) => {
      setAvailableAgents(
        agents.map((a) => ({
          id: a.name,
          name: a.name,
          framework: a.framework || "crewai",
        }))
      );
    }).catch(() => {
      // Silently fail - binding panel will show empty list
    });
  }, []);

  // Check advanced knowledge plugin availability
  useEffect(() => {
    advancedKnowledgeApi.isAvailable().then(setAdvancedAvailable).catch(() => setAdvancedAvailable(false));
  }, []);

  // Load sources
  useEffect(() => {
    const loadSources = async () => {
      setIsLoading(true);
      try {
        const { sources: data } = await knowledgeApi.getSources();
        setSources(data);
      } catch (error) {
        console.error("Failed to load sources:", error);
      } finally {
        setIsLoading(false);
      }
    };
    loadSources();
  }, []);

  const handleSearch = async (offsetOverride?: number) => {
    if (!searchQuery.trim()) return;
    const currentOffset = offsetOverride ?? searchOffset;
    setIsSearching(true);
    try {
      // GAP-070: Use options object with source_ids, threshold, and pagination
      const { results, totalResults: total } = await knowledgeApi.search(searchQuery, {
        source_ids: selectedSource ? [selectedSource.id] : undefined,
        threshold: threshold[0],
        limit: 10,
        offset: currentOffset,
      });
      if (currentOffset === 0) {
        setSearchResults(results);
      } else {
        setSearchResults(prev => [...prev, ...results]);
      }
      setTotalResults(total);
    } catch (error) {
      console.error("Search failed:", error);
      toast.error(t("searchFailed"));
    } finally {
      setIsSearching(false);
    }
  };

  const handleUpload = async (files: FileList | null) => {
    if (!files?.length) return;
    const file = files[0];

    // Show uploading state
    setUploadProgress({ stage: "uploading", progress: 0 });

    try {
      // Call real API endpoint
      await knowledgeApi.uploadSource(file, {
        name: file.name,
      });

      // Refresh sources list from backend to get accurate data
      const { sources: updatedSources } = await knowledgeApi.getSources();
      setSources(updatedSources);

      setActiveTab("sources");
      toast.success(t("upload.success"));
    } catch (error) {
      console.error("Upload failed:", error);
      toast.error(error instanceof Error ? error.message : t("upload.failed"));
    } finally {
      setUploadProgress(null);
    }
  };

  const handleDeleteSource = async (id: string) => {
    try {
      await knowledgeApi.deleteSource(id);
      setSources((prev) => prev.filter((s) => s.id !== id));
      if (selectedSource?.id === id) setSelectedSource(null);
      toast.success(t("source.deleted"));
    } catch (error) {
      toast.error(t("source.deleteFailed"));
    }
  };

  const handleBindingUpdate = (crews: string[], agents: string[]) => {
    if (!selectedSource) return;
    setSources((prev) =>
      prev.map((s) => (s.id === selectedSource.id ? { ...s, crews, agents } : s))
    );
    setSelectedSourceId(selectedSource.id);
    toast.success(t("source.bindingsUpdated"));
  };

  const handleAdvancedSearch = async () => {
    if (!advancedQuery.trim()) return;
    setIsAdvancedSearching(true);
    try {
      const { results, query_variants, strategies_used } = await advancedKnowledgeApi.query(
        advancedQuery,
        {
          multi_query: multiQueryEnabled,
          hyde: hydeEnabled,
          rerank: rerankEnabled,
          source_ids: selectedSource ? [selectedSource.id] : undefined,
        }
      );
      setAdvancedResults(results);
      setAdvancedVariants(query_variants);
      setAdvancedStrategies(strategies_used);
    } catch (error) {
      console.error("Advanced search failed:", error);
      toast.error(t("advanced.searchFailed"));
    } finally {
      setIsAdvancedSearching(false);
    }
  };

  const getTypeIcon = (type: string) => {
    switch (type) {
      case "pdf":
        return <FileText aria-hidden="true" className="w-4 h-4 text-destructive/70" />;
      case "md":
        return <File aria-hidden="true" className="w-4 h-4 text-info" />;
      default:
        return <File aria-hidden="true" className="w-4 h-4 text-muted-foreground" />;
    }
  };

  return (
    <div className="h-full flex flex-col" data-testid="knowledge-container">
      {/* Header */}
      <div className="border-b border-border p-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <BookOpen aria-hidden="true" className="w-5 h-5 text-primary" />
          <h1 className="text-xl font-semibold text-foreground">{t("title")}</h1>
          <Badge variant="secondary">{t("sourcesCount", { count: sources.length })}</Badge>
        </div>
        <Dialog open={searchOpen} onOpenChange={setSearchOpen}>
          <DialogTrigger asChild>
            <Button variant="outline" className="gap-2">
              <Search aria-hidden="true" className="w-4 h-4" />
              {t("search")}
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-2xl max-h-[80vh] overflow-hidden flex flex-col">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Search aria-hidden="true" className="w-5 h-5" />
                {t("semanticSearch")}
              </DialogTitle>
            </DialogHeader>
            <div className="space-y-4 flex-1 overflow-hidden flex flex-col">
              <div className="flex gap-2">
                <Input
                  placeholder={t("searchPlaceholder")}
                  aria-label="Search knowledge base"
                  value={searchQuery}
                  onChange={(e) => {
                    setSearchQuery(e.target.value);
                    setSearchOffset(0);
                    setSearchResults([]);
                    setTotalResults(0);
                  }}
                  onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                />
                <Button size="icon" aria-label="Search" onClick={() => handleSearch()} disabled={isSearching}>
                  {isSearching ? <Loader2 aria-hidden="true" className="w-4 h-4 motion-safe:animate-spin" /> : <Search aria-hidden="true" className="w-4 h-4" />}
                </Button>
              </div>
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span>{t("threshold")}</span>
                  <span>{threshold[0].toFixed(2)}</span>
                </div>
                <Slider value={threshold} onValueChange={(val) => {
                  setThreshold(val);
                  setSearchOffset(0);
                  setSearchResults([]);
                  setTotalResults(0);
                }} min={0} max={1} step={0.05} />
              </div>
              {selectedSource && (
                <div className="flex items-center gap-2 p-2 rounded-lg bg-muted/50">
                  {getTypeIcon(selectedSource.source_type)}
                  <span className="text-sm truncate flex-1">{selectedSource.name}</span>
                  <Button variant="ghost" size="icon" className="h-6 w-6" aria-label="Clear source filter" onClick={() => setSelectedSource(null)}>
                    <X aria-hidden="true" className="w-3 h-3" />
                  </Button>
                </div>
              )}
              {searchResults.length > 0 && (
                <div className="text-sm text-muted-foreground">
                  {t("showingResults", { shown: searchResults.length, total: totalResults })}
                </div>
              )}
              <ScrollArea className="h-[400px]">
                <div className="space-y-3 pr-4">
                  {searchResults.length === 0 && searchQuery && !isSearching && (
                    <EmptyState
                      variant="search"
                      title={t("noResultsTitle")}
                      description={t("noResultsDescription")}
                      size="sm"
                    />
                  )}
                  {searchResults.map((result, idx) => (
                    <Card
                      key={idx}
                      tabIndex={0}
                      role="button"
                      className={cn(
                        "border cursor-pointer hover:border-primary/50 transition-colors",
                        result.score >= 0.35 ? "border-success/50" : result.score >= 0.2 ? "border-amber-500/50" : "border-border"
                      )}
                      onClick={() => {
                        setSelectedChunk(result);
                        setSearchOpen(false);
                      }}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          setSelectedChunk(result);
                          setSearchOpen(false);
                        }
                      }}
                    >
                      <CardContent className="p-3">
                        <div className="flex justify-between items-center mb-2">
                          <span className="text-xs text-muted-foreground">
                            {result.metadata.source_name || (result.metadata as Record<string, unknown>).name as string || t("unknownSource")}
                          </span>
                          <Badge
                            variant="outline"
                            className={cn(
                              result.score >= 0.35 ? "text-success" :
                              result.score >= 0.2 ? "text-amber-500" : ""
                            )}
                          >
                            {result.score >= 0.35 ? t("relevance.high") :
                             result.score >= 0.2 ? t("relevance.medium") : t("relevance.low")}
                          </Badge>
                        </div>
                        <p className="text-sm line-clamp-3">{result.content}</p>
                      </CardContent>
                    </Card>
                  ))}
                  {searchResults.length > 0 && searchResults.length < totalResults && (
                    <Button
                      variant="ghost"
                      className="w-full"
                      onClick={() => {
                        const newOffset = searchResults.length;
                        setSearchOffset(newOffset);
                        handleSearch(newOffset);
                      }}
                      disabled={isSearching}
                    >
                      {isSearching ? <Loader2 aria-hidden="true" className="w-4 h-4 motion-safe:animate-spin mr-2" /> : null}
                      {t("showMoreResults")}
                    </Button>
                  )}
                </div>
              </ScrollArea>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {/* Main Content with Tabs */}
      <div className="flex-1 p-6 overflow-hidden">
        <Tabs value={activeTab} onValueChange={setActiveTab} className="h-full flex flex-col">
          <TabsList className="self-start mb-4">
            <TabsTrigger value="sources" className="gap-2">
              <BookOpen aria-hidden="true" className="w-4 h-4" />
              {t("tabs.sources")}
            </TabsTrigger>
            <TabsTrigger value="upload" className="gap-2">
              <Upload aria-hidden="true" className="w-4 h-4" />
              {t("tabs.upload")}
            </TabsTrigger>
            {advancedAvailable && (
              <TabsTrigger value="advanced" className="gap-2">
                <Search aria-hidden="true" className="w-4 h-4" />
                {t("tabs.advanced")}
              </TabsTrigger>
            )}
          </TabsList>

          {/* Sources Tab */}
          <TabsContent value="sources" className="flex-1 overflow-hidden mt-0">
            <ScrollArea className="h-full">
              {isLoading ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {Array.from({ length: 6 }).map((_, i) => (
                    <Skeleton key={i} className="h-32" />
                  ))}
                </div>
              ) : sources.length === 0 ? (
                <EmptyState
                  variant="knowledge"
                  title={t("emptyState.title")}
                  description={t("emptyState.description")}
                  action={{ label: t("emptyState.action"), onClick: () => setActiveTab("upload") }}
                />
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 pb-4">
                  {sources.map((source) => (
                    <DocumentCard
                      key={source.id}
                      source={source}
                      selected={selectedSource?.id === source.id}
                      onSelect={() => setSelectedSourceId(source.id)}
                      onDelete={() => handleDeleteSource(source.id)}
                      onBind={() => {
                        setSelectedSourceId(source.id);
                        setShowBindingPanel(true);
                      }}
                    />
                  ))}
                </div>
              )}
            </ScrollArea>
          </TabsContent>

          {/* Upload Tab */}
          <TabsContent value="upload" className="flex-1 mt-0">
            <div
              className="h-full border-2 border-dashed border-border rounded-xl flex flex-col items-center justify-center gap-4 hover:border-primary/50 transition-colors"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                handleUpload(e.dataTransfer.files);
              }}
            >
              {uploadProgress ? (
                <div className="w-64 space-y-3">
                  <div className="flex items-center justify-between text-sm">
                    <span className="capitalize flex items-center gap-2">
                      {uploadProgress.stage === "complete" ? (
                        <span className="text-success">{t("upload.complete")}</span>
                      ) : (
                        <>
                          <Loader2 aria-hidden="true" className="w-4 h-4 motion-safe:animate-spin" />
                          {uploadProgress.stage}
                        </>
                      )}
                    </span>
                    <span>{Math.round(uploadProgress.progress)}%</span>
                  </div>
                  <Progress value={uploadProgress.progress} />
                  <div className="flex justify-center gap-1">
                    {["uploading", "parsing", "chunking", "embedding"].map((stage, idx) => (
                      <div
                        key={stage}
                        className={cn(
                          "w-2 h-2 rounded-full",
                          ["uploading", "parsing", "chunking", "embedding"].indexOf(uploadProgress.stage) >= idx
                            ? "bg-primary"
                            : "bg-muted"
                        )}
                      />
                    ))}
                  </div>
                </div>
              ) : (
                <>
                  <Upload aria-hidden="true" className="w-12 h-12 text-muted-foreground" />
                  <p className="text-muted-foreground">{t("upload.dragAndDrop")}</p>
                  <Button
                    variant="outline"
                    onClick={() => document.getElementById("file-input")?.click()}
                  >
                    {t("upload.browseFiles")}
                  </Button>
                  <input
                    id="file-input"
                    type="file"
                    className="hidden"
                    accept=".pdf,.md,.txt,.docx"
                    onChange={(e) => handleUpload(e.target.files)}
                  />
                  <p className="text-xs text-muted-foreground">{t("upload.supportedFormats")}</p>
                </>
              )}
            </div>
          </TabsContent>

          {/* Advanced RAG Test Tab */}
          <TabsContent value="advanced" className="flex-1 overflow-hidden mt-0">
            <div className="space-y-4 p-1">
              {/* Query input */}
              <div className="flex gap-2">
                <Input
                  placeholder={t("advanced.queryPlaceholder")}
                  aria-label="Advanced RAG query"
                  value={advancedQuery}
                  onChange={(e) => setAdvancedQuery(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleAdvancedSearch()}
                />
                <Button onClick={handleAdvancedSearch} disabled={isAdvancedSearching}>
                  {isAdvancedSearching ? <Loader2 aria-hidden="true" className="w-4 h-4 motion-safe:animate-spin" /> : t("advanced.searchButton")}
                </Button>
              </div>

              {/* Feature toggles */}
              <div className="flex gap-4 items-center">
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={multiQueryEnabled} onChange={(e) => setMultiQueryEnabled(e.target.checked)} />
                  {t("advanced.multiQuery")}
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={hydeEnabled} onChange={(e) => setHydeEnabled(e.target.checked)} />
                  {t("advanced.hyde")}
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={rerankEnabled} onChange={(e) => setRerankEnabled(e.target.checked)} />
                  {t("advanced.reranking")}
                </label>
              </div>

              {/* Strategies and variants info */}
              {advancedStrategies.length > 0 && (
                <div className="flex gap-2 flex-wrap">
                  {advancedStrategies.map((s) => (
                    <Badge key={s} variant="secondary">{s}</Badge>
                  ))}
                </div>
              )}
              {advancedVariants.length > 0 && (
                <div className="space-y-1">
                  <p className="text-xs text-muted-foreground font-medium">{t("advanced.queryVariants")}</p>
                  {advancedVariants.map((v, i) => (
                    <p key={i} className="text-xs text-muted-foreground pl-2">- {v}</p>
                  ))}
                </div>
              )}

              {/* Results */}
              <ScrollArea className="h-[calc(100vh-400px)]">
                <div className="space-y-3 pr-4">
                  {advancedResults.length === 0 && advancedQuery && !isAdvancedSearching && (
                    <EmptyState variant="search" title={t("advanced.noResultsTitle")} description={t("advanced.noResultsDescription")} size="sm" />
                  )}
                  {advancedResults.map((result, idx) => (
                    <Card key={idx} className="border hover:border-primary/50 transition-colors">
                      <CardContent className="p-3">
                        <div className="flex justify-between items-center mb-2">
                          <span className="text-xs text-muted-foreground">
                            {result.metadata.source_name || t("unknownSource")}
                          </span>
                          <Badge variant="outline">
                            {result.score >= 0.35 ? t("relevance.high") : result.score >= 0.2 ? t("relevance.medium") : t("relevance.low")}
                          </Badge>
                        </div>
                        <p className="text-sm line-clamp-4">{result.content}</p>
                        <div className="flex gap-2 mt-2 text-xs text-muted-foreground">
                          <span>{t("advanced.score", { score: result.score.toFixed(3) })}</span>
                          {result.metadata.page !== undefined && <span>{t("advanced.page", { page: result.metadata.page })}</span>}
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </ScrollArea>
            </div>
          </TabsContent>
        </Tabs>
      </div>

      {/* Binding Panel */}
      {showBindingPanel && selectedSource && (
        <div
          className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center"
          role="dialog"
          aria-label={`Bind agents to ${selectedSource.name}`}
          onClick={() => setShowBindingPanel(false)}
          onKeyDown={(e) => { if (e.key === "Escape") setShowBindingPanel(false); }}
        >
          <div onClick={(e) => e.stopPropagation()}>
            <BindingPanel
              sourceId={selectedSource.id}
              sourceName={selectedSource.name}
              availableAgents={availableAgents}
              availableCrews={[]}
              boundAgents={selectedSource.agents}
              boundCrews={selectedSource.crews}
              onSave={async (agents, crews) => {
                handleBindingUpdate(crews, agents);
              }}
              onClose={() => setShowBindingPanel(false)}
            />
          </div>
        </div>
      )}

      {/* Chunk Viewer */}
      {selectedChunk && (
        <div
          className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4"
          role="dialog"
          aria-label="Chunk viewer"
          onClick={() => setSelectedChunk(null)}
          onKeyDown={(e) => { if (e.key === "Escape") setSelectedChunk(null); }}
        >
          <div onClick={(e) => e.stopPropagation()} className="max-w-2xl w-full max-h-[80vh]">
            <ChunkViewer
              sourceId={selectedChunk.metadata.source_name || "unknown"}
              sourceName={selectedChunk.metadata.source_name || t("searchResult")}
              chunks={[{
                id: `chunk-${selectedChunk.metadata.chunk_index ?? 0}`,
                content: selectedChunk.content,
                metadata: {
                  chunk_index: selectedChunk.metadata.chunk_index ?? 0,
                  page: selectedChunk.metadata.page,
                  source_name: selectedChunk.metadata.source_name
                }
              }]}
              totalChunks={1}
            />
          </div>
        </div>
      )}
    </div>
  );
};

export default KnowledgePage;