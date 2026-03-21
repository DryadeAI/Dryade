// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useMemo } from "react";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Wrench } from "lucide-react";
import type { AgentTool } from "@/types/api";

interface ToolAccordionProps {
  tools: AgentTool[];
}

/**
 * Parse a tool description that may contain concatenated format like:
 * "Tool Name: X Tool Arguments: {...} Tool Description: Y"
 * Returns the clean description or the original if no pattern found.
 */
function parseToolDescription(description: string): string {
  if (!description) return "";

  // Check for the concatenated format pattern
  const toolDescMatch = description.match(/Tool Description:\s*(.+?)(?:$|Tool Name:|Tool Arguments:)/i);
  if (toolDescMatch) {
    return toolDescMatch[1].trim();
  }

  // Check if description starts with "Tool Name:" which indicates the raw format
  if (description.startsWith("Tool Name:")) {
    // Try to extract just the description part
    const parts = description.split("Tool Description:");
    if (parts.length > 1) {
      return parts[parts.length - 1].trim();
    }
  }

  return description;
}

/**
 * Check if parameters object looks like a raw JSON schema (has schema metadata fields)
 * and extract the actual properties if so.
 */
function normalizeParameters(params: AgentTool["parameters"]): AgentTool["parameters"] {
  if (!params) return { type: "object", properties: {} };

  // If params has the expected structure, return as-is
  if (params.properties && typeof params.properties === "object") {
    return params;
  }

  // If params itself looks like a schema with nested properties
  if (params.type === "object" && !params.properties) {
    return { type: "object", properties: {}, required: [] };
  }

  return params;
}

const ToolAccordion = ({ tools }: ToolAccordionProps) => {
  // Normalize tool data to handle various formats
  const normalizedTools = useMemo(() =>
    tools.map(tool => ({
      ...tool,
      description: parseToolDescription(tool.description),
      parameters: normalizeParameters(tool.parameters),
    })),
    [tools]
  );

  return (
    <Accordion type="multiple" className="space-y-1">
      {normalizedTools.map((tool) => (
        <AccordionItem
          key={tool.name}
          value={tool.name}
          className="border border-border/50 rounded-lg px-3 bg-secondary/30"
        >
          <AccordionTrigger className="py-2.5 hover:no-underline text-sm">
            <span className="flex items-center gap-2">
              <Wrench size={14} className="text-primary" />
              <span className="font-mono">{tool.name}</span>
            </span>
          </AccordionTrigger>
          <AccordionContent className="pb-3 pt-1">
            <p className="text-sm text-muted-foreground mb-2">
              {tool.description}
            </p>
            {tool.parameters.properties && Object.keys(tool.parameters.properties).length > 0 && (
              <div className="mt-2">
                <span className="text-xs font-medium text-muted-foreground">
                  Parameters:
                </span>
                <div className="flex flex-wrap gap-1 mt-1">
                  {Object.entries(tool.parameters.properties).map(([name, prop]) => (
                    <span
                      key={name}
                      className="text-xs px-2 py-0.5 rounded bg-muted font-mono"
                    >
                      {name}
                      {tool.parameters.required?.includes(name) && (
                        <span className="text-destructive ml-0.5">*</span>
                      )}
                      <span className="text-muted-foreground ml-1">
                        : {(prop as { type?: string }).type || "any"}
                      </span>
                    </span>
                  ))}
                </div>
              </div>
            )}
          </AccordionContent>
        </AccordionItem>
      ))}
    </Accordion>
  );
};

export default ToolAccordion;
