// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useEffect, useMemo, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { Bot, SearchX, Settings, AlertCircle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent } from "@/components/ui/card";
import { Link, useNavigate } from "react-router-dom";
import AgentCard from "@/components/agents/AgentCard";
import AgentSearchBar from "@/components/agents/AgentSearchBar";
import FrameworkFilterTabs from "@/components/agents/FrameworkFilterTabs";
import AgentDetailPanel from "@/components/agents/AgentDetailPanel";
import EmptyState from "@/components/shared/EmptyState";
import { agentsApi } from "@/services/api";
import type { Agent, AgentFramework } from "@/types/api";

type FilterValue = AgentFramework | "all";

const AgentsPage = () => {
  const { t } = useTranslation('agents');
  const navigate = useNavigate();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeFilter, setActiveFilter] = useState<FilterValue>("all");
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);

  const loadAgents = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { agents: data } = await agentsApi.getAgents();
      setAgents(data);
    } catch (err) {
      console.error("Failed to load agents:", err);
      setError(t('error.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAgents();
  }, [loadAgents]);

  const filteredAgents = useMemo(() => {
    let result = agents;

    if (activeFilter !== "all") {
      result = result.filter(a => a.framework === activeFilter);
    }

    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      result = result.filter(a =>
        a.name.toLowerCase().includes(query) ||
        a.description.toLowerCase().includes(query)
      );
    }

    return result;
  }, [agents, activeFilter, searchQuery]);

  const counts = useMemo(() => {
    const base = searchQuery
      ? agents.filter(a => {
          const query = searchQuery.toLowerCase();
          return a.name.toLowerCase().includes(query) || a.description.toLowerCase().includes(query);
        })
      : agents;

    return {
      all: base.length,
      crewai: base.filter(a => a.framework === "crewai").length,
      langchain: base.filter(a => a.framework === "langchain").length,
      adk: base.filter(a => a.framework === "adk").length,
      a2a: base.filter(a => a.framework === "a2a").length,
      mcp: base.filter(a => a.framework === "mcp").length,
      custom: base.filter(a => a.framework === "custom").length,
    };
  }, [agents, searchQuery]);

  const handleSearch = useCallback((query: string) => {
    setSearchQuery(query);
  }, []);

  const handleFilterChange = useCallback((filter: FilterValue) => {
    setActiveFilter(filter);
  }, []);

  const handleClearFilters = () => {
    setSearchQuery("");
    setActiveFilter("all");
  };

  return (
    <div className="flex h-full">
      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <header className="shrink-0 p-6 border-b border-border">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h1 className="text-2xl font-bold text-foreground">{t('page.title')}</h1>
              <p className="text-sm text-muted-foreground">
                {t('page.subtitle')}
              </p>
            </div>
          </div>

          <div className="space-y-4">
            <AgentSearchBar onSearch={handleSearch} />
            <FrameworkFilterTabs
              activeFilter={activeFilter}
              onFilterChange={handleFilterChange}
              counts={counts}
            />
          </div>
        </header>

        {/* Grid */}
        <div className="flex-1 overflow-auto p-6">
          {loading ? (
            <div
              aria-label="Loading agents"
              className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
            >
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="glass-card p-4">
                  <div className="flex items-start justify-between mb-2">
                    <Skeleton className="h-5 w-24" />
                    <Skeleton className="h-5 w-16" />
                  </div>
                  <Skeleton className="h-10 w-full mb-3" />
                  <Skeleton className="h-4 w-20" />
                </div>
              ))}
            </div>
          ) : error ? (
            <div className="h-full flex items-center justify-center">
              <Card className="max-w-md w-full border-destructive/30">
                <CardContent className="pt-6 text-center space-y-4">
                  <AlertCircle className="w-12 h-12 text-destructive mx-auto" aria-hidden="true" />
                  <h2 className="text-lg font-semibold text-foreground">{t('error.somethingWentWrong')}</h2>
                  <p className="text-sm text-muted-foreground">{error}</p>
                  <Button onClick={loadAgents} variant="outline" className="gap-2">
                    <RefreshCw className="w-4 h-4" aria-hidden="true" />
                    {t('actions.retry')}
                  </Button>
                </CardContent>
              </Card>
            </div>
          ) : filteredAgents.length === 0 ? (
            agents.length === 0 ? (
              <EmptyState
                variant="agents"
                title={t('empty.noAgentsTitle')}
                description={t('empty.noAgentsDescription')}
                action={{
                  label: t('empty.goToSettings'),
                  onClick: () => navigate("/workspace/settings"),
                }}
                className="h-full"
                size="lg"
              />
            ) : (
              <EmptyState
                variant="search"
                title={t('empty.noMatchTitle')}
                description={t('empty.noMatchDescription')}
                action={{
                  label: t('empty.clearFilters'),
                  onClick: handleClearFilters,
                }}
                className="h-full"
              />
            )
          ) : (
            <div
              aria-label="Agents list"
              data-testid="agents-list"
              className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
            >
              {filteredAgents.map((agent) => (
                <AgentCard
                  key={agent.name}
                  agent={agent}
                  isSelected={selectedAgent === agent.name}
                  onClick={() => setSelectedAgent(agent.name)}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Detail Panel */}
      {selectedAgent && (
        <AgentDetailPanel
          agentName={selectedAgent}
          onClose={() => setSelectedAgent(null)}
        />
      )}
    </div>
  );
};

export default AgentsPage;
