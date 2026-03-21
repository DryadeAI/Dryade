// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { cn } from "@/lib/utils";
import { type WorkflowNode } from "@/types/workflow";
import { getNodeConfig, statusColors } from "@/config/nodeConfig";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { X, Play, Trash2 } from "lucide-react";

interface NodeInspectorProps {
  node: WorkflowNode | null;
  onClose: () => void;
  onUpdateNode: (id: string, updates: Partial<WorkflowNode>) => void;
  onDeleteNode: (id: string) => void;
  onRunNode: (id: string) => void;
}

const NodeInspector = ({
  node,
  onClose,
  onUpdateNode,
  onDeleteNode,
  onRunNode,
}: NodeInspectorProps) => {
  if (!node) {
    return (
      <div className="glass-card p-4 h-full flex items-center justify-center">
        <p className="text-muted-foreground text-sm text-center">
          Select a node to inspect its properties
        </p>
      </div>
    );
  }

  const config = getNodeConfig(node.type);
  const Icon = config.icon;

  return (
    <div className="glass-card p-4 h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className={cn("p-2 rounded-md", config.bgClass)}>
            <Icon size={18} className={config.colorClass} />
          </div>
          <div>
            <h3 className="font-medium text-foreground">{node.label}</h3>
            <p className="text-xs text-muted-foreground capitalize">
              {node.type} node
            </p>
          </div>
        </div>
        <Button variant="ghost" size="icon-sm" onClick={onClose}>
          <X size={16} />
        </Button>
      </div>

      {/* Status */}
      <div className="flex items-center gap-2 mb-4 p-3 rounded-lg bg-secondary/30">
        <div className={cn("status-dot", statusColors[node.status])} />
        <span className="text-sm text-foreground capitalize">{node.status}</span>
      </div>

      {/* Properties */}
      <div className="flex-1 space-y-4">
        <div className="space-y-2">
          <Label htmlFor="node-label">Label</Label>
          <Input
            id="node-label"
            value={node.label}
            onChange={(e) => onUpdateNode(node.id, { label: e.target.value })}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="node-description">Description</Label>
          <Input
            id="node-description"
            value={node.description || ""}
            onChange={(e) =>
              onUpdateNode(node.id, { description: e.target.value })
            }
            placeholder="Add a description..."
          />
        </div>

        {/* Agent (readonly display) */}
        {node.agent && (
          <div className="space-y-2">
            <Label>Agent</Label>
            <div className="p-2 rounded-md bg-secondary/30 text-sm text-foreground/80 font-mono">
              {node.agent}
            </div>
          </div>
        )}

        {/* Task (editable textarea) */}
        {node.task !== undefined && (
          <div className="space-y-2">
            <Label htmlFor="node-task">Task</Label>
            <textarea
              id="node-task"
              className="w-full min-h-[80px] p-2 rounded-md border border-border bg-background text-sm resize-y"
              value={node.task || ""}
              onChange={(e) => onUpdateNode(node.id, { task: e.target.value })}
              placeholder="Task description for the agent..."
            />
          </div>
        )}

        {/* Tool (for MCP agents) */}
        {node.agent?.startsWith("mcp-") && (
          <div className="space-y-2">
            <Label htmlFor="node-tool">Tool</Label>
            <Input
              id="node-tool"
              value={node.tool || ""}
              onChange={(e) => onUpdateNode(node.id, { tool: e.target.value })}
              placeholder="e.g. capella_open_session"
            />
            <p className="text-xs text-muted-foreground">Exact MCP tool name to call</p>
          </div>
        )}

        {/* Arguments (JSON editor for MCP agents) */}
        {node.agent?.startsWith("mcp-") && (
          <div className="space-y-2">
            <Label htmlFor="node-arguments">Arguments (JSON)</Label>
            <textarea
              id="node-arguments"
              className="w-full min-h-[60px] p-2 rounded-md border border-border bg-background text-sm font-mono resize-y"
              value={node.arguments ? JSON.stringify(node.arguments, null, 2) : "{}"}
              onChange={(e) => {
                try {
                  const parsed = JSON.parse(e.target.value);
                  onUpdateNode(node.id, { arguments: parsed });
                } catch {
                  // Don't update on invalid JSON - user is still typing
                }
              }}
              placeholder='{"param": "value"}'
            />
            <p className="text-xs text-muted-foreground">Tool parameters as JSON</p>
          </div>
        )}

        {/* Output Display */}
        {node.outputs && node.outputs.length > 0 && (
          <div className="space-y-2">
            <Label>Output</Label>
            <div className="p-3 rounded-lg bg-secondary/30 font-mono text-xs max-h-40 overflow-auto">
              {node.outputs.map((output, i) => (
                <div key={i} className="text-foreground/80">
                  {output}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="flex gap-2 mt-4 pt-4 border-t border-border">
        <Button
          variant="default"
          size="sm"
          className="flex-1"
          onClick={() => onRunNode(node.id)}
          disabled={node.status === "running"}
        >
          <Play size={14} />
          Run
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => onDeleteNode(node.id)}
          className="text-destructive hover:bg-destructive/10"
        >
          <Trash2 size={14} />
        </Button>
      </div>
    </div>
  );
};

export default NodeInspector;
