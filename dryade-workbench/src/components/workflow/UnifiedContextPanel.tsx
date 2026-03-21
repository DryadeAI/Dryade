// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useEffect, useMemo, useRef, useCallback } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Bot,
  Blocks,
  Settings2,
  Search,
  X,
  Play,
  Trash2,
  GripVertical,
  Loader2,
  ListChecks,
  History,
  FolderOpen,
  Sparkles,
  FileCode,
  Plus,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { agentsApi } from "@/services/api";
import type { Agent } from "@/types/api";
import type { ScenarioInfo, Plan } from "@/types/extended-api";
import type { WorkflowListItem } from "@/services/api";
import FrameworkBadge from "@/components/agents/FrameworkBadge";
import { RunHistoryPanel } from "@/components/workflow/RunHistoryPanel";

type PanelTab = "agents" | "inspector" | "scenarios" | "history";

interface SelectedNodeData {
  id: string;
  label: string;
  nodeType: string;
  description?: string;
  status: string;
}

interface UnifiedContextPanelProps {
  selectedNode: SelectedNodeData | null;
  onUpdateNode?: (id: string, updates: Partial<SelectedNodeData>) => void;
  onDeleteNode?: (id: string) => void;
  onRunNode?: (id: string) => void;
  onCloseInspector?: () => void;
  onAddAgent?: (agent: Agent) => void;
  width: number;
  onWidthChange: (width: number) => void;
  minWidth?: number;
  maxWidth?: number;
  // Scenarios tab props
  workflows?: ScenarioInfo[];
  userPlans?: Plan[];
  myWorkflows?: WorkflowListItem[];
  workflowsLoading?: boolean;
  selectedWorkflowId?: string | null;
  selectedPlan?: Plan | null;
  currentWorkflowId?: number | null;
  onCreateWorkflow?: () => void;
  onSelectWorkflow?: (workflow: ScenarioInfo) => void;
  onSelectPlan?: (plan: Plan) => void;
  onLoadWorkflowById?: (id: number) => void;
  // History tab props
  workflowId?: number | null;
  scenarioName?: string | null;
  planId?: number | null;
  currentExecutionId?: string | number | null;
  onViewResult?: (result: unknown) => void;
}

const tabs: { id: PanelTab; icon: typeof Bot; label: string }[] = [
  { id: "agents", icon: Bot, label: "Agents" },
  { id: "inspector", icon: Settings2, label: "Inspector" },
  { id: "scenarios", icon: ListChecks, label: "Scenarios" },
  { id: "history", icon: History, label: "History" },
];

const UnifiedContextPanel = ({
  selectedNode,
  onUpdateNode,
  onDeleteNode,
  onRunNode,
  onCloseInspector,
  onAddAgent,
  width,
  onWidthChange,
  minWidth = 280,
  maxWidth = 480,
  // Scenarios props
  workflows = [],
  userPlans = [],
  myWorkflows = [],
  workflowsLoading = false,
  selectedWorkflowId,
  selectedPlan,
  currentWorkflowId,
  onCreateWorkflow,
  onSelectWorkflow,
  onSelectPlan,
  onLoadWorkflowById,
  // History props
  scenarioName,
  planId,
  currentExecutionId,
  onViewResult,
}: UnifiedContextPanelProps) => {
  const [activeTab, setActiveTab] = useState<PanelTab>("agents");
  const [searchQuery, setSearchQuery] = useState("");
  const [isResizing, setIsResizing] = useState(false);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [agentsLoading, setAgentsLoading] = useState(true);
  const [frameworkFilter, setFrameworkFilter] = useState<string>("all");

  const panelRef = useRef<HTMLDivElement>(null);

  // Switch to inspector when node is selected
  useEffect(() => {
    if (selectedNode) {
      setActiveTab("inspector");
    }
  }, [selectedNode]);

  // Load agents
  useEffect(() => {
    const loadAgents = async () => {
      setAgentsLoading(true);
      try {
        const { agents: data } = await agentsApi.getAgents();
        setAgents(data);
      } catch (error) {
        console.error("Failed to load agents:", error);
      } finally {
        setAgentsLoading(false);
      }
    };
    loadAgents();
  }, []);

  // Filter agents
  const filteredAgents = useMemo(() => {
    let result = agents;

    if (frameworkFilter !== "all") {
      result = result.filter(a => a.framework === frameworkFilter);
    }

    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      result = result.filter(a =>
        a.name.toLowerCase().includes(query) ||
        a.description.toLowerCase().includes(query) ||
        a.tags.some(t => t.toLowerCase().includes(query))
      );
    }

    return result;
  }, [agents, frameworkFilter, searchQuery]);

  // Get unique frameworks
  const frameworks = useMemo(() => {
    const unique = [...new Set(agents.map(a => a.framework))];
    return ["all", ...unique];
  }, [agents]);

  // Resize handling
  const handleResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizing(true);
  }, []);

  useEffect(() => {
    if (!isResizing) return;

    const handleMouseMove = (e: MouseEvent) => {
      const panelRect = panelRef.current?.getBoundingClientRect();
      if (!panelRect) return;
      const newWidth = panelRect.right - e.clientX;
      onWidthChange(Math.min(Math.max(newWidth, minWidth), maxWidth));
    };

    const handleMouseUp = () => setIsResizing(false);

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    document.body.style.cursor = "ew-resize";
    document.body.style.userSelect = "none";

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, [isResizing, minWidth, maxWidth, onWidthChange]);

  // Render inspector content
  const renderInspector = () => {
    if (!selectedNode) {
      return (
        <div className="flex-1 flex items-center justify-center p-6">
          <div className="text-center text-muted-foreground">
            <Blocks size={32} className="mx-auto mb-2 opacity-50" />
            <p className="text-sm font-medium">No node selected</p>
            <p className="text-xs mt-1">Select a node to view its properties</p>
          </div>
        </div>
      );
    }

    const isRunning = selectedNode.status === "running";

    return (
      <div className="flex-1 flex flex-col min-h-0 p-4 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-foreground">{selectedNode.label}</h3>
          {onCloseInspector && (
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onCloseInspector}>
              <X size={14} />
            </Button>
          )}
        </div>

        {/* Status */}
        <div className="flex items-center gap-2 p-2 rounded-lg bg-secondary/30">
          <div className={cn(
            "w-2 h-2 rounded-full",
            selectedNode.status === "idle" && "bg-muted-foreground",
            selectedNode.status === "running" && "bg-primary animate-pulse",
            selectedNode.status === "success" && "bg-success",
            selectedNode.status === "error" && "bg-destructive"
          )} />
          <span className="text-xs text-foreground capitalize">{selectedNode.status}</span>
          <span className="text-xs text-muted-foreground ml-auto capitalize">{selectedNode.nodeType}</span>
        </div>

        {/* Editable Fields */}
        {onUpdateNode && (
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="node-label" className="text-xs">Label</Label>
              <Input
                id="node-label"
                value={selectedNode.label}
                onChange={(e) => onUpdateNode(selectedNode.id, { label: e.target.value })}
                className="h-8 text-sm"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="node-desc" className="text-xs">Description</Label>
              <Input
                id="node-desc"
                value={selectedNode.description || ""}
                onChange={(e) => onUpdateNode(selectedNode.id, { description: e.target.value })}
                placeholder="Add description..."
                className="h-8 text-sm"
              />
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-2">
          {onRunNode && (
            <Button
              variant="default"
              size="sm"
              className="flex-1 h-8 gap-1.5"
              onClick={() => onRunNode(selectedNode.id)}
              disabled={isRunning}
            >
              {isRunning ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
              {isRunning ? "Running" : "Run"}
            </Button>
          )}
          {onDeleteNode && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => onDeleteNode(selectedNode.id)}
              className="h-8 text-destructive hover:bg-destructive/10"
            >
              <Trash2 size={12} />
            </Button>
          )}
        </div>
      </div>
    );
  };

  // Render agents content
  const renderAgents = () => (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Search */}
      <div className="p-3 border-b border-border space-y-2">
        <div className="relative">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search agents..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="h-8 pl-8 pr-8 text-sm"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              <X size={14} />
            </button>
          )}
        </div>

        {/* Framework Filter */}
        <div className="flex gap-1 flex-wrap">
          {frameworks.map(fw => (
            <button
              key={fw}
              onClick={() => setFrameworkFilter(fw)}
              className={cn(
                "px-2 py-1 text-xs rounded-md capitalize transition-colors",
                frameworkFilter === fw
                  ? "bg-primary text-primary-foreground"
                  : "bg-secondary text-muted-foreground hover:bg-secondary/80"
              )}
            >
              {fw}
            </button>
          ))}
        </div>
      </div>

      {/* Agent List */}
      <ScrollArea className="flex-1">
        <div className="p-2 space-y-1.5">
          {agentsLoading ? (
            Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-20 w-full rounded-lg" />
            ))
          ) : filteredAgents.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
              <Bot size={32} className="mb-2 opacity-50" />
              <p className="text-sm font-medium">No agents found</p>
              <p className="text-xs mt-1">Try a different search</p>
            </div>
          ) : (
            filteredAgents.map(agent => (
              <button
                key={agent.id}
                onClick={() => onAddAgent?.(agent)}
                draggable
                onDragStart={(e) => {
                  e.dataTransfer.setData("agentId", agent.id);
                  e.dataTransfer.setData("agentName", agent.name);
                }}
                className={cn(
                  "w-full p-3 rounded-lg text-left transition-all duration-200",
                  "border border-border/50 bg-secondary/20",
                  "hover:border-primary/40 hover:bg-secondary/40",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                )}
              >
                <div className="flex items-start gap-3">
                  <div className="p-2 rounded-lg bg-primary/10 shrink-0">
                    <Bot size={16} className="text-primary" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-medium text-sm truncate">{agent.name}</span>
                      <FrameworkBadge framework={agent.framework} size="sm" />
                    </div>
                    <p className="text-xs text-muted-foreground line-clamp-2">
                      {agent.description}
                    </p>
                    <div className="flex flex-wrap gap-1 mt-1.5">
                      {agent.tags.slice(0, 3).map(tag => (
                        <span
                          key={tag}
                          className="px-1.5 py-0.5 text-[10px] rounded bg-muted text-muted-foreground"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              </button>
            ))
          )}
        </div>
      </ScrollArea>
    </div>
  );

  // Render scenarios content
  const renderScenarios = () => {
    const hasContent = myWorkflows.length > 0 || userPlans.length > 0 || workflows.length > 0;

    return (
      <div className="flex-1 flex flex-col min-h-0">
        {/* Create button */}
        {onCreateWorkflow && (
          <div className="p-2 border-b border-border">
            <Button
              variant="outline"
              size="sm"
              className="w-full gap-2 h-8"
              onClick={onCreateWorkflow}
            >
              <Plus size={13} />
              New Workflow
            </Button>
          </div>
        )}

        <ScrollArea className="flex-1">
          <div className="p-2 space-y-3">
            {workflowsLoading ? (
              Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full rounded-lg" />
              ))
            ) : !hasContent ? (
              <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                <ListChecks size={32} className="mb-2 opacity-50" />
                <p className="text-sm font-medium">No workflows yet</p>
                <p className="text-xs mt-1">Create one to get started</p>
              </div>
            ) : (
              <>
                {/* Custom Workflows */}
                {myWorkflows.length > 0 && (
                  <div className="space-y-1">
                    <div className="flex items-center gap-1.5 px-1 pb-0.5">
                      <FolderOpen size={11} className="text-blue-500" />
                      <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                        My Workflows
                      </span>
                    </div>
                    {myWorkflows.map((wf) => (
                      <button
                        key={`wf-${wf.id}`}
                        onClick={() => onLoadWorkflowById?.(wf.id)}
                        className={cn(
                          "w-full flex items-center justify-between px-2.5 py-2 rounded-md text-sm transition-colors text-left",
                          "hover:bg-secondary/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                          currentWorkflowId === wf.id && "bg-blue-500/10 text-blue-600 dark:text-blue-400"
                        )}
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <FolderOpen size={13} className="text-blue-500 shrink-0" />
                          <span className="truncate text-xs font-medium">{wf.name}</span>
                        </div>
                        <Badge variant="outline" className="text-[9px] ml-2 shrink-0">
                          {wf.status}
                        </Badge>
                      </button>
                    ))}
                  </div>
                )}

                {/* AI Plans */}
                {userPlans.length > 0 && (
                  <div className="space-y-1">
                    <div className="flex items-center gap-1.5 px-1 pb-0.5">
                      <Sparkles size={11} className="text-purple-500" />
                      <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                        AI Plans
                      </span>
                    </div>
                    {userPlans.map((plan) => (
                      <button
                        key={`plan-${plan.id}`}
                        onClick={() => onSelectPlan?.(plan)}
                        className={cn(
                          "w-full flex items-center justify-between px-2.5 py-2 rounded-md text-sm transition-colors text-left",
                          "hover:bg-secondary/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                          selectedPlan?.id === plan.id && "bg-purple-500/10 text-purple-600 dark:text-purple-400"
                        )}
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <Sparkles size={13} className="text-purple-500 shrink-0" />
                          <span className="truncate text-xs font-medium">{plan.name}</span>
                        </div>
                        <Badge
                          variant="outline"
                          className="text-[9px] ml-2 shrink-0 bg-purple-500/10 text-purple-500 border-purple-500/20"
                        >
                          AI
                        </Badge>
                      </button>
                    ))}
                  </div>
                )}

                {/* System Templates */}
                {workflows.length > 0 && (
                  <div className="space-y-1">
                    <div className="flex items-center gap-1.5 px-1 pb-0.5">
                      <FileCode size={11} className="text-muted-foreground" />
                      <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                        Templates
                      </span>
                    </div>
                    {workflows.map((workflow) => (
                      <button
                        key={workflow.name}
                        onClick={() => onSelectWorkflow?.(workflow)}
                        className={cn(
                          "w-full flex items-center justify-between px-2.5 py-2 rounded-md text-sm transition-colors text-left",
                          "hover:bg-secondary/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                          selectedWorkflowId === workflow.name && !selectedPlan && "bg-primary/10 text-primary"
                        )}
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <FileCode size={13} className="text-muted-foreground shrink-0" />
                          <span className="truncate text-xs font-medium">{workflow.display_name}</span>
                        </div>
                        <Badge variant="outline" className="text-[9px] ml-2 shrink-0">
                          {workflow.domain}
                        </Badge>
                      </button>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        </ScrollArea>
      </div>
    );
  };

  // Render history content
  const renderHistory = () => (
    <div className="flex-1 flex flex-col min-h-0 overflow-y-auto">
      {!scenarioName && !planId ? (
        <div className="flex flex-col items-center justify-center py-12 text-muted-foreground px-4">
          <History size={32} className="mb-2 opacity-50" />
          <p className="text-sm font-medium">No workflow selected</p>
          <p className="text-xs mt-1 text-center">Select a workflow to view its run history</p>
        </div>
      ) : (
        <RunHistoryPanel
          scenarioName={scenarioName}
          planId={planId}
          currentExecutionId={currentExecutionId}
          onViewResult={onViewResult}
        />
      )}
    </div>
  );

  return (
    <div
      ref={panelRef}
      className="flex flex-col h-full relative border-l border-border bg-card/50"
      style={{ width }}
    >
      {/* Resize Handle */}
      <div
        onMouseDown={handleResizeStart}
        className={cn(
          "absolute left-0 top-0 bottom-0 w-1.5 cursor-ew-resize z-10 group",
          "hover:bg-primary/30 transition-colors",
          isResizing && "bg-primary/50"
        )}
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize panel"
      >
        <div className={cn(
          "absolute left-0.5 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity",
          isResizing && "opacity-100"
        )}>
          <GripVertical size={12} className="text-primary" />
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center border-b border-border p-1 gap-0.5 overflow-x-auto" role="tablist">
        {tabs.map(tab => {
          const isActive = activeTab === tab.id;
          const hasContent = tab.id === "inspector" && selectedNode;

          return (
            <Tooltip key={tab.id}>
              <TooltipTrigger asChild>
                <button
                  role="tab"
                  aria-selected={isActive}
                  onClick={() => setActiveTab(tab.id)}
                  className={cn(
                    "flex items-center gap-1 px-2 py-1.5 rounded-md text-sm font-medium transition-all",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    isActive
                      ? "bg-primary/10 text-primary border border-primary/30"
                      : "text-muted-foreground hover:text-foreground hover:bg-secondary/50",
                    hasContent && !isActive && "relative after:absolute after:top-1 after:right-1 after:w-1.5 after:h-1.5 after:bg-primary after:rounded-full"
                  )}
                >
                  <tab.icon size={14} />
                  <span className="text-[11px] whitespace-nowrap">{tab.label}</span>
                </button>
              </TooltipTrigger>
              <TooltipContent side="bottom">{tab.label}</TooltipContent>
            </Tooltip>
          );
        })}
      </div>

      {/* Tab Content */}
      {activeTab === "agents" && renderAgents()}
      {activeTab === "inspector" && renderInspector()}
      {activeTab === "scenarios" && renderScenarios()}
      {activeTab === "history" && renderHistory()}
    </div>
  );
};

export default UnifiedContextPanel;
