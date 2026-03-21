// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { memo, useEffect, useState } from "react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
  DropdownMenuLabel,
} from "@/components/ui/dropdown-menu";
import {
  Plus,
  Clipboard,
  MousePointer2,
  Maximize,
  RotateCcw,
  Cpu,
  Bot,
  GitBranch,
  Wrench,
  ArrowRightCircle,
  ArrowLeftCircle,
  Bookmark,
  Grid3X3,
  Download,
  Upload,
  Loader2,
  ShieldCheck,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { type NodeType } from "@/types/workflow";
import { type Agent, type AgentFramework } from "@/types/api";
import { agentsApi } from "@/services/api";
import { getFrameworkStyle, frameworkStyles } from "@/config/frameworkConfig";

interface CanvasContextMenuProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  hasClipboard: boolean;
  position: { x: number; y: number };
  snapToGrid?: boolean;
  onAddNode: (type: NodeType, agentName?: string) => void;
  onPaste: () => void;
  onSelectAll: () => void;
  onFitView: () => void;
  onResetZoom: () => void;
  onToggleGrid?: () => void;
  onSaveAsTemplate?: () => void;
  onExportJson?: () => void;
  onImportJson?: () => void;
}

// Basic node types (non-agent)
const basicNodeOptions: { type: NodeType; label: string; icon: typeof Cpu }[] = [
  { type: "input", label: "Input", icon: ArrowRightCircle },
  { type: "output", label: "Output", icon: ArrowLeftCircle },
  { type: "decision", label: "Decision", icon: GitBranch },
  { type: "tool", label: "Tool", icon: Wrench },
  { type: "task", label: "Task", icon: Cpu },
  { type: "approval", label: "Approval Step", icon: ShieldCheck },
];

// Framework order for display
const frameworkOrder: (AgentFramework | 'custom')[] = [
  'crewai',
  'langchain',
  'adk',
  'a2a',
  'mcp',
  'custom',
];

const CanvasContextMenu = ({
  open,
  onOpenChange,
  hasClipboard,
  position,
  snapToGrid,
  onAddNode,
  onPaste,
  onSelectAll,
  onFitView,
  onResetZoom,
  onToggleGrid,
  onSaveAsTemplate,
  onExportJson,
  onImportJson,
}: CanvasContextMenuProps) => {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(false);

  // Fetch agents when menu opens
  useEffect(() => {
    if (open && agents.length === 0) {
      setLoading(true);
      agentsApi
        .getAgents()
        .then(({ agents: data }) => setAgents(data))
        .catch(console.error)
        .finally(() => setLoading(false));
    }
  }, [open, agents.length]);

  // Group agents by framework
  const agentsByFramework = agents.reduce((acc, agent) => {
    const framework = agent.framework || 'custom';
    if (!acc[framework]) acc[framework] = [];
    acc[framework].push(agent);
    return acc;
  }, {} as Record<string, Agent[]>);

  return (
    <DropdownMenu open={open} onOpenChange={onOpenChange}>
      {/* Invisible trigger positioned at mouse location */}
      <DropdownMenuTrigger asChild>
        <div
          className="fixed w-0 h-0"
          style={{
            left: position.x,
            top: position.y,
            pointerEvents: "none",
          }}
        />
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-56" align="start" side="bottom">
        {/* Add Node submenu */}
        <DropdownMenuSub>
          <DropdownMenuSubTrigger className="gap-2">
            <Plus size={14} />
            Add Node
          </DropdownMenuSubTrigger>
          <DropdownMenuSubContent className="w-52">
            {/* Basic node types */}
            <DropdownMenuLabel className="text-[10px] text-muted-foreground uppercase tracking-wider">
              Basic Nodes
            </DropdownMenuLabel>
            {basicNodeOptions.map((option) => (
              <DropdownMenuItem
                key={option.type}
                onClick={() => onAddNode(option.type)}
                className="gap-2"
              >
                <option.icon size={14} />
                {option.label}
              </DropdownMenuItem>
            ))}

            <DropdownMenuSeparator />

            {/* Agents grouped by framework */}
            <DropdownMenuLabel className="text-[10px] text-muted-foreground uppercase tracking-wider">
              Agents
            </DropdownMenuLabel>

            {loading ? (
              <DropdownMenuItem disabled className="gap-2 text-muted-foreground">
                <Loader2 size={14} className="animate-spin" />
                Loading agents...
              </DropdownMenuItem>
            ) : agents.length === 0 ? (
              <DropdownMenuItem disabled className="gap-2 text-muted-foreground">
                <Bot size={14} />
                No agents available
              </DropdownMenuItem>
            ) : (
              frameworkOrder.map((framework) => {
                const frameworkAgents = agentsByFramework[framework];
                if (!frameworkAgents || frameworkAgents.length === 0) return null;

                const style = getFrameworkStyle(framework);
                const FrameworkIcon = style.icon;

                return (
                  <DropdownMenuSub key={framework}>
                    <DropdownMenuSubTrigger className={cn("gap-2", style.hoverBg)}>
                      <FrameworkIcon size={14} className={style.color} />
                      <span>{style.label}</span>
                    </DropdownMenuSubTrigger>
                    <DropdownMenuSubContent className="w-56 max-h-64 overflow-y-auto">
                      {frameworkAgents.map((agent) => (
                        <DropdownMenuItem
                          key={agent.name}
                          onClick={() => onAddNode("agent", agent.name)}
                          className={cn("gap-2 flex-col items-start", style.hoverBg)}
                        >
                          <div className="flex items-center gap-2 w-full">
                            <div
                              className={cn(
                                "w-6 h-6 rounded flex items-center justify-center shrink-0",
                                style.bgColor
                              )}
                            >
                              <FrameworkIcon size={12} className={style.color} />
                            </div>
                            <span className="font-medium truncate flex-1">
                              {agent.name}
                            </span>
                          </div>
                          {agent.description && (
                            <p className="text-[10px] text-muted-foreground line-clamp-2 pl-8">
                              {agent.description}
                            </p>
                          )}
                        </DropdownMenuItem>
                      ))}
                    </DropdownMenuSubContent>
                  </DropdownMenuSub>
                );
              })
            )}

            {/* Quick add generic agent */}
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={() => onAddNode("agent")}
              className="gap-2 text-muted-foreground"
            >
              <Bot size={14} />
              Generic Agent
            </DropdownMenuItem>
          </DropdownMenuSubContent>
        </DropdownMenuSub>

        <DropdownMenuItem
          onClick={onPaste}
          disabled={!hasClipboard}
          className="gap-2"
        >
          <Clipboard size={14} />
          Paste
          <DropdownMenuShortcut>⌘V</DropdownMenuShortcut>
        </DropdownMenuItem>

        <DropdownMenuSeparator />

        <DropdownMenuItem onClick={onSelectAll} className="gap-2">
          <MousePointer2 size={14} />
          Select All
          <DropdownMenuShortcut>⌘A</DropdownMenuShortcut>
        </DropdownMenuItem>

        <DropdownMenuSeparator />

        <DropdownMenuItem onClick={onFitView} className="gap-2">
          <Maximize size={14} />
          Fit View
          <DropdownMenuShortcut>⌘1</DropdownMenuShortcut>
        </DropdownMenuItem>

        <DropdownMenuItem onClick={onResetZoom} className="gap-2">
          <RotateCcw size={14} />
          Reset Zoom
          <DropdownMenuShortcut>⌘0</DropdownMenuShortcut>
        </DropdownMenuItem>

        {onToggleGrid && (
          <DropdownMenuItem onClick={onToggleGrid} className="gap-2">
            <Grid3X3 size={14} />
            {snapToGrid ? "Disable" : "Enable"} Grid Snap
            <DropdownMenuShortcut>⌘G</DropdownMenuShortcut>
          </DropdownMenuItem>
        )}

        <DropdownMenuSeparator />

        {onSaveAsTemplate && (
          <DropdownMenuItem onClick={onSaveAsTemplate} className="gap-2">
            <Bookmark size={14} />
            Save as Template
          </DropdownMenuItem>
        )}

        {onExportJson && (
          <DropdownMenuItem onClick={onExportJson} className="gap-2">
            <Download size={14} />
            Export as JSON
          </DropdownMenuItem>
        )}

        {onImportJson && (
          <DropdownMenuItem onClick={onImportJson} className="gap-2">
            <Upload size={14} />
            Import from JSON
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
};

export default memo(CanvasContextMenu);
