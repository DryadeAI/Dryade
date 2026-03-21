// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { cn } from "@/lib/utils";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import StreamingOutput from "./StreamingOutput";
import {
  CheckCircle2,
  Circle,
  Loader2,
  XCircle,
} from "lucide-react";

type NodeStatus = 'pending' | 'running' | 'completed' | 'failed';

interface ExecutionNode {
  id: string;
  type: string;
  status: NodeStatus;
  output?: string;
  error?: string;
}

interface NodeOutputAccordionProps {
  nodes: ExecutionNode[];
  currentNodeId: string | null;
  className?: string;
}

const statusConfig: Record<NodeStatus, { icon: typeof Circle; color: string; bgColor: string }> = {
  pending: { icon: Circle, color: "text-muted-foreground", bgColor: "bg-muted/50" },
  running: { icon: Loader2, color: "text-primary", bgColor: "bg-primary/10" },
  completed: { icon: CheckCircle2, color: "text-green-500", bgColor: "bg-green-500/10" },
  failed: { icon: XCircle, color: "text-destructive", bgColor: "bg-destructive/10" },
};

const NodeOutputAccordion = ({
  nodes,
  currentNodeId,
  className,
}: NodeOutputAccordionProps) => {
  // Running node should be expanded by default
  const defaultValue = currentNodeId ? [currentNodeId] : [];

  return (
    <Accordion
      type="multiple"
      defaultValue={defaultValue}
      value={currentNodeId ? [currentNodeId] : undefined}
      className={cn("space-y-2", className)}
    >
      {nodes.map((node, index) => {
        const config = statusConfig[node.status];
        const StatusIcon = config.icon;
        const isRunning = node.status === 'running';
        const isCurrent = node.id === currentNodeId;

        return (
          <AccordionItem
            key={node.id}
            value={node.id}
            className={cn(
              "border rounded-lg overflow-hidden",
              isCurrent && "ring-2 ring-primary ring-offset-2 ring-offset-background"
            )}
          >
            <AccordionTrigger className={cn("px-4 py-3 hover:no-underline", config.bgColor)}>
              <div className="flex items-center gap-3 flex-1">
                {/* Step number */}
                <div
                  className={cn(
                    "w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium",
                    node.status === 'completed' && "bg-green-500 text-white",
                    node.status === 'running' && "bg-primary text-primary-foreground",
                    node.status === 'failed' && "bg-destructive text-destructive-foreground",
                    node.status === 'pending' && "bg-muted text-muted-foreground"
                  )}
                >
                  {index + 1}
                </div>

                {/* Status icon */}
                <StatusIcon
                  className={cn(
                    "w-4 h-4",
                    config.color,
                    isRunning && "animate-spin"
                  )}
                />

                {/* Node name */}
                <span className="font-medium text-sm flex-1 text-left truncate">
                  {node.id}
                </span>

                {/* Status badge */}
                <Badge
                  variant="outline"
                  className={cn("text-xs capitalize", config.color)}
                >
                  {node.status}
                </Badge>
              </div>
            </AccordionTrigger>

            <AccordionContent className="px-4 pb-4">
              {node.error ? (
                <div className="p-3 rounded-lg bg-destructive/10 text-destructive text-sm">
                  {node.error}
                </div>
              ) : node.output ? (
                <StreamingOutput
                  content={node.output}
                  isStreaming={isRunning}
                />
              ) : isRunning ? (
                <StreamingOutput content="" isStreaming />
              ) : (
                <p className="text-sm text-muted-foreground italic">
                  Waiting to execute...
                </p>
              )}
            </AccordionContent>
          </AccordionItem>
        );
      })}
    </Accordion>
  );
};

export default NodeOutputAccordion;
