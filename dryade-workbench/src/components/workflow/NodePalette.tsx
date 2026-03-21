// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { cn } from "@/lib/utils";
import { type NodeType } from "@/types/workflow";
import { nodeConfigs } from "@/config/nodeConfig";
import { GripVertical } from "lucide-react";

interface NodePaletteProps {
  onAddNode: (type: NodeType) => void;
}

const NodePalette = ({ onAddNode }: NodePaletteProps) => {
  const nodeTypes = Object.entries(nodeConfigs) as [NodeType, typeof nodeConfigs.input][];

  return (
    <div className="glass-card p-4 space-y-3">
      <h3 className="text-sm font-medium text-foreground mb-3">Node Templates</h3>
      <p className="text-xs text-muted-foreground mb-4">
        Drag nodes onto the canvas or click to add
      </p>
      <div className="space-y-2">
        {nodeTypes.map(([type, config]) => {
          const Icon = config.icon;
          return (
            <button
              key={type}
              onClick={() => onAddNode(type)}
              className={cn(
                "w-full flex items-center gap-3 p-3 rounded-lg border transition-all duration-200",
                "bg-secondary/30 border-border hover:border-primary/40 hover:bg-secondary/50",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                "cursor-grab active:cursor-grabbing group"
              )}
              draggable
              onDragStart={(e) => {
                e.dataTransfer.setData("nodeType", type);
                e.dataTransfer.effectAllowed = "move";
              }}
            >
              <GripVertical 
                size={14} 
                className="text-muted-foreground/40 group-hover:text-muted-foreground transition-colors" 
              />
              <div className={cn("p-2 rounded-md", config.bgClass)}>
                <Icon size={18} className={config.colorClass} />
              </div>
              <div className="text-left flex-1">
                <p className="text-sm font-medium text-foreground">{config.label}</p>
                <p className="text-xs text-muted-foreground">
                  {config.description || `${type} node`}
                </p>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
};

export default NodePalette;
