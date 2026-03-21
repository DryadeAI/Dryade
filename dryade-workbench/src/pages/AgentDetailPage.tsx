// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useEffect } from "react";
import { useTranslation, Trans } from "react-i18next";
import { useParams, useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import PageBreadcrumb from "@/components/shared/PageBreadcrumb";
import EmptyState from "@/components/shared/EmptyState";
import FrameworkBadge from "@/components/agents/FrameworkBadge";
import ToolCard from "@/components/agents/ToolCard";
import AgentExecutionForm from "@/components/agents/AgentExecutionForm";
import ExecutionResult from "@/components/agents/ExecutionResult";
import { agentsApi } from "@/services/api";
import { Play, Settings, Wrench, FileText, AlertCircle } from "lucide-react";
import { toast } from "sonner";
import type { AgentDetail, AgentTool, AgentInvokeResponse } from "@/types/api";

const AgentDetailPage = () => {
  const { t } = useTranslation('agents');
  const { name } = useParams<{ name: string }>();
  const navigate = useNavigate();
  const [agent, setAgent] = useState<AgentDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isExecuting, setIsExecuting] = useState(false);
  const [executionResult, setExecutionResult] = useState<AgentInvokeResponse | null>(null);
  const [showExecuteForm, setShowExecuteForm] = useState(false);

  useEffect(() => {
    const loadAgent = async () => {
      if (!name) return;
      setIsLoading(true);
      try {
        const data = await agentsApi.getAgent(name);
        setAgent(data);
      } catch (error) {
        console.error("Failed to load agent:", error);
        toast.error(t('error.loadAgentFailed'));
      } finally {
        setIsLoading(false);
      }
    };
    loadAgent();
  }, [name]);

  const handleExecute = async (task: string, context?: Record<string, unknown>) => {
    if (!name) return;
    setIsExecuting(true);
    try {
      const result = await agentsApi.invokeAgent(name, task, context);
      setExecutionResult(result);
      toast.success(t('detail.executionCompleted'));
    } catch (error) {
      toast.error(t('error.executionFailed'));
    } finally {
      setIsExecuting(false);
    }
  };

  if (isLoading) {
    return (
      <div className="h-full overflow-auto p-6">
        <div className="max-w-5xl mx-auto space-y-6">
          <Skeleton className="h-5 w-48" />
          <div className="flex items-center gap-4">
            <Skeleton className="h-10 w-10 rounded-lg" />
            <div className="space-y-2">
              <Skeleton className="h-6 w-48" />
              <Skeleton className="h-4 w-32" />
            </div>
          </div>
          <Skeleton className="h-64" />
        </div>
      </div>
    );
  }

  if (!agent) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center space-y-4">
          <AlertCircle className="w-12 h-12 text-muted-foreground mx-auto" aria-hidden="true" />
          <h2 className="text-xl font-semibold">{t('detail.notFoundTitle')}</h2>
          <p className="text-muted-foreground">{t('detail.notFoundDescription', { name })}</p>
          <Button onClick={() => navigate("/workspace/agents")}>
            {t('detail.backToAgents')}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto p-6">
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Breadcrumb */}
        <PageBreadcrumb
          items={[
            { label: t('detail.breadcrumbAgents'), href: "/workspace/agents" },
            { label: agent.name },
          ]}
        />

        {/* Header */}
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-semibold text-foreground">{agent.name}</h1>
              <FrameworkBadge framework={agent.framework} />
            </div>
            <p className="text-muted-foreground mt-1">{agent.description || t('detail.noDescription')}</p>
          </div>
          <div className="flex gap-2">
            <Button onClick={() => setShowExecuteForm(true)}>
              <Play className="w-4 h-4 mr-2" aria-hidden="true" />
              {t('detail.execute')}
            </Button>
            <Button variant="outline">
              <Settings className="w-4 h-4 mr-2" aria-hidden="true" />
              {t('detail.configure')}
            </Button>
          </div>
        </div>

        {/* Execution Form */}
        {showExecuteForm && (
          <Card>
            <CardHeader>
              <CardTitle>{t('detail.executeAgent')}</CardTitle>
              <CardDescription>{t('detail.runWithTask')}</CardDescription>
            </CardHeader>
            <CardContent>
              <AgentExecutionForm
                agentName={agent.name}
                onExecute={handleExecute}
                onCancel={() => setShowExecuteForm(false)}
                isExecuting={isExecuting}
              />
            </CardContent>
          </Card>
        )}

        {/* Execution Result */}
        {executionResult && (
          <Card>
            <CardHeader>
              <CardTitle>{t('detail.executionResult')}</CardTitle>
            </CardHeader>
            <CardContent>
              <ExecutionResult
                result={executionResult}
                onExecuteAgain={() => setShowExecuteForm(true)}
              />
            </CardContent>
          </Card>
        )}

        {/* Tabs */}
        <Tabs defaultValue="tools" className="space-y-4">
          <TabsList>
            <TabsTrigger value="tools" className="gap-2">
              <Wrench className="w-4 h-4" aria-hidden="true" />
              {t('detail.toolsTab', { count: agent.tools?.length || 0 })}
            </TabsTrigger>
            <TabsTrigger value="docs" className="gap-2">
              <FileText className="w-4 h-4" aria-hidden="true" />
              {t('detail.documentationTab')}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="tools">
            <Card>
              <CardHeader>
                <CardTitle>{t('detail.availableTools')}</CardTitle>
                <CardDescription>{t('detail.toolsDescription')}</CardDescription>
              </CardHeader>
              <CardContent>
                {agent.tools && agent.tools.length > 0 ? (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {agent.tools.map((tool: AgentTool) => (
                      <ToolCard key={tool.name} tool={tool} />
                    ))}
                  </div>
                ) : (
                  <EmptyState
                    variant="default"
                    title={t('detail.noToolsConfigured')}
                    description="This agent has no tools configured. Tools allow the agent to interact with external services and APIs."
                    size="sm"
                  />
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="docs">
            <Card>
              <CardHeader>
                <CardTitle>{t('detail.documentationTitle')}</CardTitle>
                <CardDescription>{t('detail.documentationDescription')}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <h3 className="font-medium mb-2">{t('detail.overview')}</h3>
                  <p className="text-sm text-muted-foreground">
                    <Trans
                      i18nKey="detail.overviewText"
                      ns="agents"
                      values={{ framework: agent.framework }}
                      components={{ strong: <strong /> }}
                    />
                  </p>
                </div>
                <Separator />
                <div>
                  <h3 className="font-medium mb-2">{t('detail.apiEndpoint')}</h3>
                  <pre className="bg-muted p-4 rounded-lg overflow-x-auto text-sm">
                    POST /api/agents/{agent.name}/invoke
                  </pre>
                </div>
                <Separator />
                <div>
                  <h3 className="font-medium mb-2">{t('detail.configuration')}</h3>
                  <p className="text-sm text-muted-foreground">
                    <Trans
                      i18nKey="detail.version"
                      ns="agents"
                      values={{ version: agent.version }}
                      components={{ code: <code /> }}
                    />
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {t('detail.toolsCount', { count: agent.tools?.length || 0 })}
                  </p>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
};

export default AgentDetailPage;
