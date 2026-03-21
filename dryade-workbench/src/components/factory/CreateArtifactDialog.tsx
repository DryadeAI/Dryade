// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// CreateArtifactDialog - Multi-step wizard for creating factory artifacts
// Steps: browse (template gallery) > configure (form) > creating (progress) > done (result)

import { useState, useCallback } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import {
  Users,
  Link2,
  Cpu,
  Server,
  Wrench,
  BookOpen,
  Bot,
  Sparkles,
  ChevronLeft,
  Check,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { factoryApi } from "@/services/api";
import type { CreateArtifactRequest, CreationResult } from "@/services/api/factory";
import { getFrameworkStyle } from "@/config/frameworkConfig";
import FactoryProgressBar from "./FactoryProgressBar";
import { cn } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";

// ---------------------------------------------------------------------------
// Template definitions
// ---------------------------------------------------------------------------

interface Template {
  artifact_type: string;
  framework: string;
  label: string;
  description: string;
  icon: LucideIcon;
}

const TEMPLATES: Template[] = [
  // Agents
  { artifact_type: "agent", framework: "crewai", label: "CrewAI Agent", description: "Multi-agent crew with role-based collaboration", icon: Users },
  { artifact_type: "agent", framework: "langchain", label: "LangChain Agent", description: "Tool-calling agent with LangChain framework", icon: Link2 },
  { artifact_type: "agent", framework: "adk", label: "ADK Agent", description: "Google Agent Development Kit agent", icon: Cpu },
  { artifact_type: "agent", framework: "custom", label: "Custom Agent", description: "Minimal agent with custom implementation", icon: Bot },
  // Tools
  { artifact_type: "tool", framework: "mcp_function", label: "MCP Function", description: "Single-purpose tool function", icon: Wrench },
  { artifact_type: "tool", framework: "mcp_server", label: "MCP Server", description: "Tool server exposing multiple endpoints", icon: Server },
  // Skills
  { artifact_type: "skill", framework: "skill", label: "Skill", description: "Reusable prompt template or instruction set", icon: BookOpen },
];

const TYPE_SECTIONS = [
  { type: "agent", label: "Agents" },
  { type: "tool", label: "Tools" },
  { type: "skill", label: "Skills" },
] as const;

// Framework options per artifact type (for configure step selects)
const FRAMEWORK_OPTIONS: Record<string, { value: string; label: string }[]> = {
  agent: [
    { value: "crewai", label: "CrewAI" },
    { value: "langchain", label: "LangChain" },
    { value: "adk", label: "ADK" },
    { value: "custom", label: "Custom" },
  ],
  tool: [
    { value: "mcp_function", label: "MCP Function" },
    { value: "mcp_server", label: "MCP Server" },
  ],
  skill: [
    { value: "skill", label: "Skill" },
  ],
};

type WizardStep = "browse" | "configure" | "creating" | "done";

interface CreateArtifactDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: () => void;
}

const INITIAL_FORM: CreateArtifactRequest = {
  goal: "",
  suggested_name: "",
  artifact_type: "",
  framework: "",
  test_task: "",
  max_test_iterations: 3,
  fast_path: false,
};

const CreateArtifactDialog = ({
  open,
  onOpenChange,
  onCreated,
}: CreateArtifactDialogProps) => {
  const [step, setStep] = useState<WizardStep>("browse");
  const [formData, setFormData] = useState<CreateArtifactRequest>({ ...INITIAL_FORM });
  const [isCreating, setIsCreating] = useState(false);
  const [creationResult, setCreationResult] = useState<CreationResult | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Reset state when dialog opens/closes
  const handleOpenChange = useCallback(
    (nextOpen: boolean) => {
      if (!nextOpen) {
        // Reset on close
        setStep("browse");
        setFormData({ ...INITIAL_FORM });
        setIsCreating(false);
        setCreationResult(null);
        setShowAdvanced(false);
      }
      onOpenChange(nextOpen);
    },
    [onOpenChange]
  );

  const handleTemplateSelect = (template: Template) => {
    setFormData((prev) => ({
      ...prev,
      artifact_type: template.artifact_type,
      framework: template.framework,
    }));
    setStep("configure");
  };

  const handleStartFromScratch = () => {
    setFormData({ ...INITIAL_FORM });
    setStep("configure");
  };

  const handleCreate = async () => {
    if (!formData.goal.trim()) {
      toast.error("Please describe what you want to create");
      return;
    }

    setStep("creating");
    setIsCreating(true);

    try {
      // Build request, omitting empty optional fields
      const request: CreateArtifactRequest = { goal: formData.goal.trim() };
      if (formData.suggested_name?.trim()) request.suggested_name = formData.suggested_name.trim();
      if (formData.artifact_type) request.artifact_type = formData.artifact_type;
      if (formData.framework) request.framework = formData.framework;
      if (formData.test_task?.trim()) request.test_task = formData.test_task.trim();
      if (formData.max_test_iterations !== undefined && formData.max_test_iterations !== 3) {
        request.max_test_iterations = formData.max_test_iterations;
      }
      if (formData.fast_path) request.fast_path = true;

      const result = await factoryApi.create(request);
      setCreationResult(result);
      setStep("done");
    } catch (error) {
      console.error("Factory creation failed:", error);
      toast.error(
        error instanceof Error ? error.message : "Failed to create artifact"
      );
      setStep("configure");
    } finally {
      setIsCreating(false);
    }
  };

  const handleDone = () => {
    onCreated();
    handleOpenChange(false);
  };

  const updateField = <K extends keyof CreateArtifactRequest>(
    key: K,
    value: CreateArtifactRequest[K]
  ) => {
    setFormData((prev) => ({ ...prev, [key]: value }));
  };

  const currentFrameworkOptions =
    formData.artifact_type && FRAMEWORK_OPTIONS[formData.artifact_type]
      ? FRAMEWORK_OPTIONS[formData.artifact_type]
      : [];

  // -----------------------------------------------------------------------
  // Step renderers
  // -----------------------------------------------------------------------

  const renderBrowseStep = () => (
    <div className="space-y-6">
      {TYPE_SECTIONS.map((section) => {
        const templates = TEMPLATES.filter((t) => t.artifact_type === section.type);
        return (
          <div key={section.type}>
            <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
              {section.label}
            </h4>
            <div className="grid grid-cols-2 gap-2">
              {templates.map((tmpl) => {
                const style = getFrameworkStyle(tmpl.framework);
                const Icon = tmpl.icon;
                return (
                  <button
                    key={`${tmpl.artifact_type}-${tmpl.framework}`}
                    onClick={() => handleTemplateSelect(tmpl)}
                    className={cn(
                      "flex items-start gap-3 p-3 rounded-lg border text-left transition-colors",
                      "border-border hover:border-primary/50 hover:bg-muted/50"
                    )}
                  >
                    <div
                      className={cn(
                        "shrink-0 w-8 h-8 rounded-md flex items-center justify-center",
                        style.bgColor
                      )}
                    >
                      <Icon className={cn("w-4 h-4", style.color)} />
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-foreground">
                        {tmpl.label}
                      </p>
                      <p className="text-xs text-muted-foreground line-clamp-2">
                        {tmpl.description}
                      </p>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}

      {/* Start from scratch */}
      <button
        onClick={handleStartFromScratch}
        className={cn(
          "w-full flex items-center gap-3 p-3 rounded-lg border border-dashed text-left transition-colors",
          "border-border hover:border-primary/50 hover:bg-muted/50"
        )}
      >
        <div className="shrink-0 w-8 h-8 rounded-md flex items-center justify-center bg-muted">
          <Sparkles className="w-4 h-4 text-muted-foreground" />
        </div>
        <div>
          <p className="text-sm font-medium text-foreground">Start from scratch</p>
          <p className="text-xs text-muted-foreground">
            Describe your goal and let the factory decide the best approach
          </p>
        </div>
      </button>
    </div>
  );

  const renderConfigureStep = () => (
    <div className="space-y-4">
      {/* Goal (required) */}
      <div className="space-y-2">
        <Label htmlFor="goal">Goal *</Label>
        <Textarea
          id="goal"
          placeholder="Describe what you want to create in natural language..."
          value={formData.goal}
          onChange={(e) => updateField("goal", e.target.value)}
          rows={3}
        />
      </div>

      {/* Suggested name */}
      <div className="space-y-2">
        <Label htmlFor="name">Name (optional)</Label>
        <Input
          id="name"
          placeholder="my-agent-name"
          value={formData.suggested_name || ""}
          onChange={(e) => updateField("suggested_name", e.target.value)}
        />
      </div>

      {/* Artifact type */}
      <div className="space-y-2">
        <Label>Artifact type</Label>
        <Select
          value={formData.artifact_type || ""}
          onValueChange={(v) => {
            updateField("artifact_type", v);
            // Reset framework when type changes
            const firstFramework = FRAMEWORK_OPTIONS[v]?.[0]?.value || "";
            updateField("framework", firstFramework);
          }}
        >
          <SelectTrigger>
            <SelectValue placeholder="Auto-detect from goal" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="agent">Agent</SelectItem>
            <SelectItem value="tool">Tool</SelectItem>
            <SelectItem value="skill">Skill</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Framework */}
      {currentFrameworkOptions.length > 0 && (
        <div className="space-y-2">
          <Label>Framework</Label>
          <Select
            value={formData.framework || ""}
            onValueChange={(v) => updateField("framework", v)}
          >
            <SelectTrigger>
              <SelectValue placeholder="Select framework" />
            </SelectTrigger>
            <SelectContent>
              {currentFrameworkOptions.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {/* Fast path toggle */}
      <div className="flex items-center justify-between py-1">
        <div className="space-y-0.5">
          <Label htmlFor="fast-path">Fast path</Label>
          <p className="text-xs text-muted-foreground">
            Scaffold only, test in background
          </p>
        </div>
        <Switch
          id="fast-path"
          checked={formData.fast_path || false}
          onCheckedChange={(checked) => updateField("fast_path", checked)}
        />
      </div>

      {/* Advanced options (collapsed) */}
      <button
        type="button"
        onClick={() => setShowAdvanced(!showAdvanced)}
        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        {showAdvanced ? (
          <ChevronUp className="w-3 h-3" />
        ) : (
          <ChevronDown className="w-3 h-3" />
        )}
        Advanced options
      </button>

      {showAdvanced && (
        <div className="space-y-4 pl-2 border-l-2 border-border">
          {/* Test task */}
          <div className="space-y-2">
            <Label htmlFor="test-task">Test task (optional)</Label>
            <Textarea
              id="test-task"
              placeholder="Custom test task for validation..."
              value={formData.test_task || ""}
              onChange={(e) => updateField("test_task", e.target.value)}
              rows={2}
            />
          </div>

          {/* Max test iterations */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>Max test iterations</Label>
              <span className="text-xs text-muted-foreground">
                {formData.max_test_iterations ?? 3}
              </span>
            </div>
            <Slider
              value={[formData.max_test_iterations ?? 3]}
              onValueChange={([v]) => updateField("max_test_iterations", v)}
              min={1}
              max={10}
              step={1}
            />
          </div>
        </div>
      )}
    </div>
  );

  const renderCreatingStep = () => (
    <div className="py-8 px-4">
      <FactoryProgressBar
        isActive={isCreating}
        artifactName={formData.suggested_name || undefined}
      />
    </div>
  );

  const renderDoneStep = () => {
    if (!creationResult) return null;
    const style = getFrameworkStyle(creationResult.framework);
    return (
      <div className="space-y-4 py-4">
        <div className="flex items-center gap-3">
          <div className={cn("w-10 h-10 rounded-lg flex items-center justify-center", style.bgColor)}>
            <Check className={cn("w-5 h-5", style.color)} />
          </div>
          <div>
            <p className="text-sm font-semibold text-foreground">
              {creationResult.artifact_name}
            </p>
            <p className="text-xs text-muted-foreground">
              {creationResult.artifact_type} / {style.label || creationResult.framework}
            </p>
          </div>
        </div>

        <div className="rounded-lg border border-border bg-muted/30 p-3 space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-muted-foreground">Status</span>
            <span className={creationResult.test_passed ? "text-success" : "text-warning"}>
              {creationResult.test_passed ? "Tests passed" : "Tests pending"}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Test iterations</span>
            <span className="text-foreground">{creationResult.test_iterations}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Duration</span>
            <span className="text-foreground">{creationResult.duration_seconds.toFixed(1)}s</span>
          </div>
          {creationResult.deduplication_warnings.length > 0 && (
            <div className="pt-1 border-t border-border">
              <p className="text-xs text-amber-500">
                {creationResult.deduplication_warnings.join("; ")}
              </p>
            </div>
          )}
        </div>

        <p className="text-xs text-muted-foreground">{creationResult.message}</p>
      </div>
    );
  };

  // -----------------------------------------------------------------------
  // Dialog chrome
  // -----------------------------------------------------------------------

  const stepTitle: Record<WizardStep, string> = {
    browse: "Create Artifact",
    configure: "Configure",
    creating: "Creating...",
    done: "Created",
  };

  const stepDescription: Record<WizardStep, string> = {
    browse: "Choose a template or start from scratch",
    configure: "Describe your goal and customize options",
    creating: "The factory pipeline is running",
    done: "Your artifact has been created",
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{stepTitle[step]}</DialogTitle>
          <DialogDescription>{stepDescription[step]}</DialogDescription>
        </DialogHeader>

        {step === "browse" && renderBrowseStep()}
        {step === "configure" && renderConfigureStep()}
        {step === "creating" && renderCreatingStep()}
        {step === "done" && renderDoneStep()}

        <DialogFooter>
          {step === "configure" && (
            <>
              <Button
                variant="ghost"
                onClick={() => setStep("browse")}
              >
                <ChevronLeft className="w-4 h-4 mr-1" />
                Back
              </Button>
              <Button
                onClick={handleCreate}
                disabled={!formData.goal.trim()}
              >
                Create
              </Button>
            </>
          )}
          {step === "done" && (
            <Button onClick={handleDone}>Close</Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default CreateArtifactDialog;
