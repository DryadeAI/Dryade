// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useEffect, useCallback, useMemo } from "react";
import { cn } from "@/lib/utils";
import { type NodeType, type WorkflowNode } from "@/types/workflow";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Blocks,
  ListTodo,
  Search,
  X,
  Play,
  Trash2,
  ChevronDown,
  Loader2,
  AlertCircle,
  Copy,
  CheckCircle2,
  XCircle,
  FileText,
  Wand2,
  Sparkles,
  Save,
} from "lucide-react";
import { getNodeConfig, statusColors } from "@/config/nodeConfig";
import { getFrameworkStyle } from "@/config/frameworkConfig";
import { agentsApi, plansApi } from "@/services/api";
import { usePlanner } from "@/hooks/usePlanner";
import PropertiesPanel from "./PropertiesPanel";
import { Star, BookOpen, MessageSquare, Send } from "lucide-react";

// GAP-P4: Plan template type
interface PlanTemplate {
  name: string;
  description: string;
  category: string;
  parameters?: Array<{ name: string; description: string; default?: string }>;
}

// Types - chat removed as it's in main nav
type SidebarTab = "nodes" | "planner";

interface AgentCard {
  id: string;
  name: string;
  type: NodeType;
  description: string;
  tags: string[];
  framework: string;
}


interface SidebarPanelProps {
  selectedNode: WorkflowNode | null;
  onAddNode: (type: NodeType) => void;
  onUpdateNode: (id: string, updates: Partial<WorkflowNode>) => void;
  onDeleteNode: (id: string) => void;
  onRunNode: (id: string) => void;
  onCloseInspector: () => void;
  /** Callback when a plan is saved/loaded - should update canvas and URL */
  onPlanLoaded?: (planId: number, nodes: WorkflowNode[], edges: { from: string; to: string }[]) => void;
  /** Workflow ID for passing to PropertiesPanel (approval actions) */
  workflowId?: number;
  /** @deprecated Use ResizablePanel wrapper instead */
  width?: number;
  /** @deprecated Use ResizablePanel wrapper instead */
  onWidthChange?: (width: number) => void;
  /** @deprecated Use ResizablePanel wrapper instead */
  minWidth?: number;
  /** @deprecated Use ResizablePanel wrapper instead */
  maxWidth?: number;
}

// Tab configuration - removed duplicate Chat tab (Chat is in main nav)
const tabs: { id: SidebarTab; icon: typeof Blocks; label: string; shortcut: string }[] = [
  { id: "nodes", icon: Blocks, label: "Agents", shortcut: "[" },
  { id: "planner", icon: ListTodo, label: "Planner", shortcut: "]" },
];

const SidebarPanel = ({
  selectedNode,
  onAddNode,
  onUpdateNode,
  onDeleteNode,
  onRunNode,
  onCloseInspector,
  onPlanLoaded,
  workflowId,
  width: _width,
  onWidthChange: _onWidthChange,
  minWidth: _minWidth = 240,
  maxWidth: _maxWidth = 480,
}: SidebarPanelProps) => {
  const [activeTab, setActiveTab] = useState<SidebarTab>("nodes");
  const [searchQuery, setSearchQuery] = useState("");
  const [chatOptionsOpen, setChatOptionsOpen] = useState(false);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [agents, setAgents] = useState<AgentCard[]>([]);
  const [expandedFrameworks, setExpandedFrameworks] = useState<Set<string>>(new Set(['crewai']));

  // Planner hook for AI workflow generation
  const planner = usePlanner();

  // GAP-P4: Plan template picker state
  const [planTemplates, setPlanTemplates] = useState<PlanTemplate[]>([]);
  const [showTemplatePicker, setShowTemplatePicker] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<PlanTemplate | null>(null);
  const [templateParams, setTemplateParams] = useState<Record<string, string>>({});
  const [templateLoading, setTemplateLoading] = useState(false);

  // GAP-P3: Plan feedback widget state
  const [feedbackRating, setFeedbackRating] = useState<number>(0);
  const [feedbackComment, setFeedbackComment] = useState('');
  const [feedbackSubmitted, setFeedbackSubmitted] = useState(false);
  const [feedbackPlanId, setFeedbackPlanId] = useState<number | null>(null);

  // GAP-P4: Load plan templates on mount
  useEffect(() => {
    plansApi.getTemplates().then(result => {
      setPlanTemplates((result.templates || []) as PlanTemplate[]);
    }).catch(console.error);
  }, []);

  // GAP-P3: Submit feedback for a plan
  const handleSubmitFeedback = useCallback(async () => {
    if (!feedbackPlanId || feedbackRating === 0) return;
    try {
      await plansApi.submitFeedback(feedbackPlanId, feedbackRating, feedbackComment || undefined);
      setFeedbackSubmitted(true);
      toast.success("Feedback submitted");
    } catch (err) {
      console.error("Failed to submit feedback:", err);
      toast.error("Failed to submit feedback");
    }
  }, [feedbackPlanId, feedbackRating, feedbackComment]);

  // GAP-P4: Instantiate a template
  const handleInstantiateTemplate = useCallback(async () => {
    if (!selectedTemplate) return;
    setTemplateLoading(true);
    try {
      const plan = await plansApi.instantiateTemplate(selectedTemplate.name, templateParams);
      if (plan && onPlanLoaded) {
        // Convert plan nodes to workflow nodes for canvas
        const workflowNodes: WorkflowNode[] = (plan.nodes || []).map((n: Record<string, unknown>, index: number) => ({
          id: n.id,
          type: 'task' as const,
          label: n.agent || n.label || 'Task',
          description: n.task || n.description || '',
          agent: n.agent,
          task: n.task || n.description,
          position: n.position || { x: 200, y: 100 + index * 120 },
          status: 'idle' as const,
        }));
        const edges = (plan.edges || []).map((e: Record<string, unknown>) => ({
          from: e.source || e.from,
          to: e.target || e.to,
        }));
        onPlanLoaded(plan.id, workflowNodes, edges);
        setShowTemplatePicker(false);
        setSelectedTemplate(null);
        setTemplateParams({});
        toast.success(`Template "${selectedTemplate.name}" loaded`);
      }
    } catch (err) {
      console.error("Failed to instantiate template:", err);
      toast.error("Failed to load template");
    } finally {
      setTemplateLoading(false);
    }
  }, [selectedTemplate, templateParams, onPlanLoaded]);

  // Map backend Agent to frontend AgentCard
  const mapAgentToCard = (agent: { name: string; description: string; tags: string[]; framework?: string }): AgentCard => ({
    id: agent.name,
    name: agent.name,
    type: 'agent' as NodeType,  // Default all to agent type
    description: agent.description,
    tags: agent.tags || [],
    framework: agent.framework || 'custom',
  });

  // Load agents from backend
  useEffect(() => {
    const loadAgents = async () => {
      setCatalogLoading(true);
      setCatalogError(null);
      try {
        const response = await agentsApi.getAgents();
        const mappedAgents = response.agents.map(mapAgentToCard);
        setAgents(mappedAgents);
      } catch (error) {
        console.error("Failed to load agents:", error);
        setCatalogError("Failed to load agent catalog");
      } finally {
        setCatalogLoading(false);
      }
    };
    loadAgents();
  }, []);

  // Filter agents based on search
  const filteredAgents = useMemo(() => {
    if (!searchQuery.trim()) return agents;
    const query = searchQuery.toLowerCase();
    return agents.filter(
      (agent) =>
        agent.name.toLowerCase().includes(query) ||
        agent.description.toLowerCase().includes(query) ||
        agent.tags.some((tag) => tag.toLowerCase().includes(query))
    );
  }, [searchQuery, agents]);

  // Group agents by framework
  const groupedAgents = useMemo(() => {
    const groups = new Map<string, AgentCard[]>();
    filteredAgents.forEach((agent) => {
      const framework = agent.framework || 'custom';
      if (!groups.has(framework)) {
        groups.set(framework, []);
      }
      groups.get(framework)!.push(agent);
    });
    return groups;
  }, [filteredAgents]);

  // Toggle framework expansion
  const toggleFramework = useCallback((framework: string) => {
    setExpandedFrameworks((prev) => {
      const next = new Set(prev);
      if (next.has(framework)) {
        next.delete(framework);
      } else {
        next.add(framework);
      }
      return next;
    });
  }, []);


  // Keyboard navigation for tabs
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA") return;

      // Ctrl+Alt+[ or ] for tab switching
      if (e.ctrlKey && e.altKey) {
        const currentIndex = tabs.findIndex((t) => t.id === activeTab);
        if (e.key === "[" || e.key === "ArrowLeft") {
          e.preventDefault();
          const newIndex = currentIndex > 0 ? currentIndex - 1 : tabs.length - 1;
          setActiveTab(tabs[newIndex].id);
        } else if (e.key === "]" || e.key === "ArrowRight") {
          e.preventDefault();
          const newIndex = currentIndex < tabs.length - 1 ? currentIndex + 1 : 0;
          setActiveTab(tabs[newIndex].id);
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [activeTab]);

  // Render node inspector when a node is selected
  const renderNodeInspector = () => {
    if (!selectedNode) return null;

    const config = getNodeConfig(selectedNode.type);
    const Icon = config.icon;

    return (
      <div className="p-4 border-b border-border animate-fade-in">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <div className={cn("p-2 rounded-md", config.bgClass)}>
              <Icon size={18} className={config.colorClass} />
            </div>
            <div>
              <h3 className="font-medium text-foreground text-sm">{selectedNode.label}</h3>
              <p className="text-xs text-muted-foreground capitalize">{selectedNode.type}</p>
            </div>
          </div>
          <Button variant="ghost" size="icon-sm" onClick={onCloseInspector}>
            <X size={14} />
          </Button>
        </div>

        <div className="flex items-center gap-2 mb-3 p-2 rounded-lg bg-secondary/30">
          {selectedNode.status === 'running' && (
            <Loader2 size={12} className="animate-spin text-primary" />
          )}
          {selectedNode.status === 'success' && (
            <CheckCircle2 size={12} className="text-success" />
          )}
          {selectedNode.status === 'error' && (
            <XCircle size={12} className="text-destructive" />
          )}
          {selectedNode.status !== 'running' && selectedNode.status !== 'success' && selectedNode.status !== 'error' && (
            <div className={cn("status-dot", statusColors[selectedNode.status])} />
          )}
          <span className="text-xs text-foreground capitalize">{selectedNode.status}</span>
        </div>

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

        {/* Enhanced Output Display */}
        {selectedNode.outputs && selectedNode.outputs.length > 0 && (
          <div className="space-y-2 mt-3">
            <div className="flex items-center justify-between">
              <Label className="text-xs flex items-center gap-1.5">
                <FileText size={12} />
                Output
              </Label>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6"
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(selectedNode.outputs!.join("\n"));
                    toast.success("Output copied to clipboard");
                  } catch (e) {
                    toast.error("Failed to copy");
                  }
                }}
              >
                <Copy size={12} />
              </Button>
            </div>
            <ScrollArea className="h-[120px] rounded-md border border-border">
              <div className="p-2 bg-secondary/20 font-mono text-xs">
                {selectedNode.outputs.map((output, i) => (
                  <div key={i} className="text-foreground/80 whitespace-pre-wrap break-all">
                    {output.length > 500 ? (
                      <>
                        {output.slice(0, 500)}
                        <span className="text-muted-foreground">... ({output.length - 500} more chars)</span>
                      </>
                    ) : output}
                  </div>
                ))}
              </div>
            </ScrollArea>
          </div>
        )}

        {/* PropertiesPanel for approval node config (design-time + runtime) */}
        {selectedNode.type === 'approval' && (
          <div className="mt-3 border-t border-border pt-3">
            <PropertiesPanel
              selectedNode={{
                id: selectedNode.id,
                type: 'approval',
                position: selectedNode.position,
                data: {
                  ...selectedNode.config,
                  status: selectedNode.status,
                  label: selectedNode.label,
                  description: selectedNode.description,
                },
              } as unknown as Parameters<typeof ApprovalNodePanel>[0]['node']}
              onNodeUpdate={(nodeId, data) => onUpdateNode(nodeId, data as Record<string, unknown>)}
              onEdgeUpdate={() => {}}
              workflowId={workflowId}
              onClearPendingApproval={(nodeId) => {
                onUpdateNode(nodeId, { status: 'running' });
              }}
            />
          </div>
        )}

        <div className="flex gap-2 mt-3">
          <Button
            variant="default"
            size="sm"
            className="flex-1 h-8"
            onClick={() => onRunNode(selectedNode.id)}
            disabled={selectedNode.status === "running"}
          >
            <Play size={12} />
            Run
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => onDeleteNode(selectedNode.id)}
            className="h-8 text-destructive hover:bg-destructive/10"
          >
            <Trash2 size={12} />
          </Button>
        </div>
      </div>
    );
  };

  // Render tab content
  const renderTabContent = () => {
    switch (activeTab) {
      case "nodes":
        return (
          <div className="flex-1 flex flex-col min-h-0">
            {/* Search */}
            <div className="p-3 border-b border-border">
              <div className="relative">
                <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder="Search agents, tools, tags..."
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
            </div>

            {/* Agent Catalog */}
            <div className="flex-1 overflow-y-auto p-3 space-y-2">
              {catalogLoading ? (
                <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
                  <Loader2 size={24} className="animate-spin mb-2" />
                  <p className="text-sm">Loading catalog...</p>
                </div>
              ) : catalogError ? (
                <div className="flex flex-col items-center justify-center py-8 text-destructive">
                  <AlertCircle size={24} className="mb-2" />
                  <p className="text-sm">{catalogError}</p>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="mt-2"
                    onClick={() => {
                      const loadAgents = async () => {
                        setCatalogLoading(true);
                        setCatalogError(null);
                        try {
                          const response = await agentsApi.getAgents();
                          const mappedAgents = response.agents.map(mapAgentToCard);
                          setAgents(mappedAgents);
                        } catch (error) {
                          console.error("Failed to load agents:", error);
                          setCatalogError("Failed to load agent catalog");
                        } finally {
                          setCatalogLoading(false);
                        }
                      };
                      loadAgents();
                    }}
                  >
                    Retry
                  </Button>
                </div>
              ) : filteredAgents.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
                  <Search size={24} className="mb-2 opacity-50" />
                  <p className="text-sm">No agents found</p>
                  <p className="text-xs mt-1">Try a different search term</p>
                </div>
              ) : (
                Array.from(groupedAgents.entries()).map(([framework, frameworkAgents]) => {
                  const isExpanded = expandedFrameworks.has(framework);
                  const style = getFrameworkStyle(framework);
                  const FrameworkIcon = style.icon;

                  return (
                    <Collapsible
                      key={framework}
                      open={isExpanded}
                      onOpenChange={() => toggleFramework(framework)}
                    >
                      <CollapsibleTrigger asChild>
                        <button
                          className={cn(
                            "w-full flex items-center gap-2 p-2 rounded-lg transition-all duration-200",
                            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                            style.hoverBg
                          )}
                        >
                          <div className={cn("p-1.5 rounded-md", style.bgColor)}>
                            <FrameworkIcon size={14} className={style.color} />
                          </div>
                          <span className="text-sm font-medium text-foreground">
                            {style.label}
                          </span>
                          <ChevronDown
                            size={16}
                            className={cn(
                              "ml-auto text-muted-foreground transition-transform duration-200 shrink-0",
                              isExpanded && "rotate-180"
                            )}
                          />
                        </button>
                      </CollapsibleTrigger>
                      <CollapsibleContent className="space-y-2 pt-2 pl-2">
                        {frameworkAgents.map((agent) => {
                          return (
                            <button
                              key={agent.id}
                              onClick={() => onAddNode(agent.type)}
                              className={cn(
                                "w-full flex items-start gap-3 p-3 rounded-lg border transition-all duration-200",
                                "bg-secondary/20 border-border",
                                style.hoverBg,
                                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                              )}
                              draggable
                              onDragStart={(e) => e.dataTransfer.setData("nodeType", agent.type)}
                            >
                              <div className={cn("p-2 rounded-md shrink-0", style.bgColor)}>
                                <FrameworkIcon size={16} className={style.color} />
                              </div>
                              <div className="text-left min-w-0">
                                <p className="text-sm font-medium text-foreground truncate">{agent.name}</p>
                                <p className="text-xs text-muted-foreground line-clamp-1">{agent.description}</p>
                                <div className="flex flex-wrap gap-1 mt-1.5">
                                  {agent.tags.map((tag) => (
                                    <span
                                      key={tag}
                                      className="px-1.5 py-0.5 text-[10px] rounded bg-muted text-muted-foreground"
                                    >
                                      {tag}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            </button>
                          );
                        })}
                      </CollapsibleContent>
                    </Collapsible>
                  );
                })
              )}
            </div>
          </div>
        );

      case "planner":
        return (
          <div className="flex-1 flex flex-col min-h-0 p-3 gap-3">
            {/* Input Section */}
            <div className="space-y-2">
              <Label className="text-xs font-medium">Describe your workflow</Label>
              <Textarea
                value={planner.prompt}
                onChange={(e) => planner.setPrompt(e.target.value)}
                placeholder="e.g., Research a topic, analyze the findings, and create a summary report..."
                className="min-h-[100px] resize-none"
                disabled={planner.isGenerating}
              />
              <Button
                onClick={() => planner.generate()}
                disabled={!planner.prompt.trim() || planner.isGenerating}
                className="w-full gap-2"
              >
                {planner.isGenerating ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Wand2 size={14} />
                )}
                {planner.isGenerating ? "Generating..." : "Generate Workflow"}
              </Button>
            </div>

            {/* Error Display */}
            {planner.error && (
              <div className="p-2 rounded-md bg-destructive/10 border border-destructive/20 text-destructive text-sm">
                {planner.error}
              </div>
            )}

            {/* GAP-P5: Clarification questions UI */}
            {planner.clarification && (
              <div className="p-3 rounded-md bg-amber-500/10 border border-amber-500/20 space-y-2">
                <p className="text-sm font-medium text-amber-700 dark:text-amber-400">Please clarify:</p>
                {planner.clarification.context && (
                  <p className="text-xs text-muted-foreground">{planner.clarification.context}</p>
                )}
                <ul className="list-disc list-inside space-y-1">
                  {planner.clarification.questions.map((q, i) => (
                    <li key={i} className="text-sm text-foreground">{q}</li>
                  ))}
                </ul>
                <p className="text-xs text-muted-foreground">Update your prompt above to address these questions, then re-generate.</p>
              </div>
            )}

            {/* Generated Plan Preview */}
            {planner.generatedPlan && (
              <div className="flex-1 flex flex-col gap-3 min-h-0">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Sparkles size={14} className="text-purple-500" />
                    <span className="text-sm font-medium">Generated Plan</span>
                  </div>
                  <Button variant="ghost" size="icon" className="h-7 w-7" onClick={planner.clear}>
                    <Trash2 size={14} />
                  </Button>
                </div>

                <ScrollArea className="flex-1">
                  <div className="space-y-2">
                    <h4 className="font-medium">{planner.generatedPlan.name}</h4>
                    {planner.generatedPlan.description && (
                      <p className="text-sm text-muted-foreground">{planner.generatedPlan.description}</p>
                    )}
                    <div className="flex items-center gap-2">
                      <Badge variant="secondary" className="text-xs">
                        {planner.generatedPlan.nodes.length} steps
                      </Badge>
                      <Badge variant="outline" className="text-xs">
                        {Math.round(planner.generatedPlan.confidence * 100)}% confidence
                      </Badge>
                    </div>

                    {/* Node List */}
                    <div className="mt-3 space-y-2">
                      {planner.generatedPlan.nodes.map((node, i) => (
                        <div key={node.id} className="p-2 rounded-md bg-secondary/50 text-sm">
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-muted-foreground">{i + 1}.</span>
                            <span className="font-medium">{node.agent}</span>
                          </div>
                          <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{node.task}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                </ScrollArea>

                <Button onClick={async () => {
                  const workflowId = await planner.save();
                  if (workflowId && planner.generatedPlan) {
                    // Convert plan nodes to workflow nodes for canvas
                    const workflowNodes: WorkflowNode[] = planner.generatedPlan.nodes.map((n, index) => ({
                      id: n.id,
                      type: 'task' as const,
                      label: n.agent,
                      description: n.task,
                      agent: n.agent,
                      task: n.task,
                      position: n.position || { x: 200, y: 100 + index * 120 },
                      status: 'idle' as const,
                    }));

                    // Convert edges to connection format
                    const edges = planner.generatedPlan.edges.map(e => ({
                      from: e.from,
                      to: e.to,
                    }));

                    // Notify parent to load into canvas and update URL
                    onPlanLoaded?.(workflowId, workflowNodes, edges);
                    toast.success("Workflow saved and loaded");
                  }
                }} className="gap-2">
                  <Save size={14} />
                  Save as Workflow
                </Button>
              </div>
            )}

            {/* Empty State with template picker */}
            {!planner.generatedPlan && !planner.isGenerating && (
              <>
                {/* GAP-P4: Template Picker */}
                <div className="border-t border-border pt-3">
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full gap-2"
                    onClick={() => setShowTemplatePicker(!showTemplatePicker)}
                  >
                    <BookOpen size={14} />
                    {showTemplatePicker ? "Hide Templates" : "Browse Templates"}
                  </Button>
                </div>

                {showTemplatePicker && (
                  <div className="space-y-2">
                    <Label className="text-xs font-medium">Plan Templates</Label>
                    {planTemplates.length === 0 ? (
                      <p className="text-xs text-muted-foreground text-center py-2">
                        No templates available
                      </p>
                    ) : (
                      <ScrollArea className="max-h-[250px]">
                        <div className="space-y-2">
                          {planTemplates.map(tpl => (
                            <button
                              key={tpl.name}
                              onClick={() => {
                                setSelectedTemplate(selectedTemplate?.name === tpl.name ? null : tpl);
                                setTemplateParams({});
                              }}
                              className={cn(
                                "w-full text-left p-2 rounded-md border transition-all text-sm",
                                selectedTemplate?.name === tpl.name
                                  ? "bg-primary/10 border-primary/30"
                                  : "bg-secondary/20 border-border hover:bg-secondary/40"
                              )}
                            >
                              <span className="font-medium">{tpl.name}</span>
                              <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                                {tpl.description}
                              </p>
                              <Badge variant="outline" className="mt-1 text-[10px]">
                                {tpl.category}
                              </Badge>
                            </button>
                          ))}
                        </div>
                      </ScrollArea>
                    )}

                    {/* Parameter form for selected template */}
                    {selectedTemplate && (
                      <div className="space-y-2 border-t border-border pt-2">
                        <Label className="text-xs font-medium">
                          {selectedTemplate.name} Parameters
                        </Label>
                        {(selectedTemplate.parameters || []).map(param => (
                          <div key={param.name} className="space-y-1">
                            <Label className="text-[11px] text-muted-foreground">
                              {param.name}: {param.description}
                            </Label>
                            <Input
                              value={templateParams[param.name] || ''}
                              onChange={e => setTemplateParams(prev => ({
                                ...prev, [param.name]: e.target.value,
                              }))}
                              placeholder={param.default || ''}
                              className="h-7 text-xs"
                            />
                          </div>
                        ))}
                        <Button
                          onClick={handleInstantiateTemplate}
                          disabled={templateLoading}
                          className="w-full gap-2"
                          size="sm"
                        >
                          {templateLoading ? (
                            <Loader2 size={14} className="animate-spin" />
                          ) : (
                            <Sparkles size={14} />
                          )}
                          Use Template
                        </Button>
                      </div>
                    )}
                  </div>
                )}

                {!showTemplatePicker && (
                  <div className="flex-1 flex items-center justify-center text-muted-foreground">
                    <div className="text-center">
                      <Wand2 size={32} className="mx-auto mb-2 opacity-50" />
                      <p className="text-sm">Describe a workflow to generate</p>
                      <p className="text-xs mt-1">or browse templates above</p>
                    </div>
                  </div>
                )}
              </>
            )}

            {/* GAP-P3: Plan Feedback Widget - shows after plan is saved */}
            {planner.generatedPlan && !feedbackSubmitted && (
              <div className="border-t border-border pt-3 space-y-2">
                <Label className="text-xs font-medium flex items-center gap-1.5">
                  <MessageSquare size={12} />
                  Rate this plan
                </Label>
                <div className="flex items-center gap-1">
                  {[1, 2, 3, 4, 5].map(star => (
                    <button
                      key={star}
                      onClick={() => {
                        setFeedbackRating(star);
                        // Try to extract planId from URL
                        const params = new URLSearchParams(window.location.search);
                        const planId = params.get('planId');
                        if (planId) setFeedbackPlanId(Number(planId));
                      }}
                      className="p-0.5 transition-colors"
                    >
                      <Star
                        size={18}
                        className={cn(
                          "transition-colors",
                          star <= feedbackRating
                            ? "fill-yellow-400 text-yellow-400"
                            : "text-muted-foreground hover:text-yellow-300"
                        )}
                      />
                    </button>
                  ))}
                </div>
                {feedbackRating > 0 && (
                  <>
                    <Textarea
                      value={feedbackComment}
                      onChange={(e) => setFeedbackComment(e.target.value)}
                      placeholder="Optional comment..."
                      className="min-h-[50px] text-xs resize-none"
                    />
                    <Button
                      onClick={handleSubmitFeedback}
                      size="sm"
                      className="w-full gap-2"
                      disabled={!feedbackPlanId}
                    >
                      <Send size={12} />
                      Submit Feedback
                    </Button>
                  </>
                )}
              </div>
            )}

            {feedbackSubmitted && (
              <div className="border-t border-border pt-3">
                <p className="text-xs text-muted-foreground text-center">
                  Thank you for your feedback!
                </p>
              </div>
            )}
          </div>
        );

    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Tabs */}
      <div
        className="flex items-center border-b border-border p-1.5 gap-1 overflow-x-auto shrink-0"
        role="tablist"
        aria-label="Sidebar tabs"
      >
        {tabs.map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <Tooltip key={tab.id}>
              <TooltipTrigger asChild>
                <button
                  role="tab"
                  aria-selected={isActive}
                  tabIndex={0}
                  onClick={() => setActiveTab(tab.id)}
                  className={cn(
                    "flex items-center justify-center gap-1.5 px-2.5 py-2 rounded-md text-sm font-medium transition-all duration-200 shrink-0",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
                    isActive
                      ? "bg-primary/10 text-primary border border-primary/30"
                      : "text-muted-foreground hover:text-foreground hover:bg-secondary/50"
                  )}
                >
                  <tab.icon size={18} />
                  <span className="text-xs whitespace-nowrap">
                    {tab.label}
                  </span>
                </button>
              </TooltipTrigger>
              <TooltipContent side="bottom" className="flex items-center gap-2">
                <span>{tab.label}</span>
                {tab.shortcut && (
                  <kbd className="px-1.5 py-0.5 rounded bg-muted text-muted-foreground text-xs font-mono">
                    Ctrl+Alt+{tab.shortcut}
                  </kbd>
                )}
              </TooltipContent>
            </Tooltip>
          );
        })}
      </div>

      {/* Selected Node Inspector */}
      {selectedNode && renderNodeInspector()}

      {/* Tab Content */}
      {renderTabContent()}
    </div>
  );
};

export default SidebarPanel;
