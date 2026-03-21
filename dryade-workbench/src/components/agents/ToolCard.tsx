// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useMemo } from "react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { ChevronDown, ChevronRight, Wrench } from "lucide-react";
import type { AgentTool } from "@/types/api";

interface ToolCardProps {
  tool: AgentTool;
  expanded?: boolean;
  onToggle?: () => void;
  className?: string;
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

const getPlaceholderExample = (
  name: string,
  type: string,
  enumValues?: string[]
): string => {
  // If enum, show first value
  if (enumValues && enumValues.length > 0) {
    return enumValues[0];
  }
  // Common parameter name patterns
  const nameLower = name.toLowerCase();
  if (nameLower.includes("name")) return "e.g., John Doe";
  if (nameLower.includes("email")) return "e.g., user@example.com";
  if (nameLower.includes("url")) return "e.g., https://example.com";
  if (nameLower.includes("path") || nameLower.includes("file"))
    return "e.g., /path/to/file.txt";
  if (nameLower.includes("query") || nameLower.includes("search"))
    return "e.g., search term";
  if (nameLower.includes("id")) return "e.g., abc123";
  if (nameLower.includes("date")) return "e.g., 2024-01-15";
  if (
    nameLower.includes("count") ||
    nameLower.includes("limit") ||
    nameLower.includes("number")
  )
    return "e.g., 10";
  if (
    nameLower.includes("message") ||
    nameLower.includes("text") ||
    nameLower.includes("content")
  )
    return "e.g., Your message here";
  // Type-based fallbacks
  if (type === "string") return "e.g., text value";
  if (type === "integer" || type === "number") return "e.g., 42";
  if (type === "boolean") return "true or false";
  if (type === "array") return "e.g., [item1, item2]";
  if (type === "object") return 'e.g., {"key": "value"}';
  return "Enter value";
};

const ToolCard = ({
  tool,
  expanded = false,
  onToggle,
  className,
}: ToolCardProps) => {
  const [isOpen, setIsOpen] = useState(expanded);

  const handleToggle = () => {
    setIsOpen(!isOpen);
    onToggle?.();
  };

  // Normalize the tool description in case it contains concatenated format
  const cleanDescription = useMemo(() => parseToolDescription(tool.description), [tool.description]);

  const requiredParams = tool.parameters.required || [];
  const properties = tool.parameters.properties || {};

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <div
        className={cn(
          "rounded-lg border border-border bg-card overflow-hidden",
          className
        )}
      >
        <CollapsibleTrigger asChild>
          <button
            onClick={handleToggle}
            className="w-full flex items-center gap-3 px-4 py-3 hover:bg-muted/30 transition-colors text-left"
          >
            <div className="p-1.5 rounded bg-primary/10">
              <Wrench className="w-4 h-4 text-primary" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-medium text-sm truncate">{tool.name}</p>
              <p className="text-xs text-muted-foreground truncate">
                {cleanDescription}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant="secondary" className="text-xs">
                {Object.keys(properties).length} params
              </Badge>
              {isOpen ? (
                <ChevronDown className="w-4 h-4 text-muted-foreground" />
              ) : (
                <ChevronRight className="w-4 h-4 text-muted-foreground" />
              )}
            </div>
          </button>
        </CollapsibleTrigger>

        <CollapsibleContent>
          <div className="px-4 pb-4 space-y-3 border-t border-border/50 pt-3">
            {/* Parameters */}
            {Object.entries(properties).length > 0 ? (
              <div className="space-y-2">
                <p className="text-xs font-medium text-muted-foreground mb-2">
                  Parameters
                </p>
                <div className="rounded-md border border-border overflow-hidden">
                  <table className="w-full text-sm">
                    <tbody className="divide-y divide-border">
                      {Object.entries(properties).map(([name, prop]) => {
                        const property = prop as {
                          type?: string;
                          description?: string;
                          enum?: string[];
                        };
                        const isRequired = requiredParams.includes(name);
                        const example = getPlaceholderExample(
                          name,
                          property.type || "string",
                          property.enum
                        );

                        return (
                          <tr key={name} className="hover:bg-muted/30">
                            <td className="px-3 py-2 align-top">
                              <div className="flex items-center gap-1.5">
                                <code className="font-mono text-primary text-xs">
                                  {name}
                                </code>
                                {isRequired && (
                                  <span className="text-destructive text-[10px]">
                                    *
                                  </span>
                                )}
                              </div>
                              <span className="text-[10px] text-muted-foreground">
                                {property.type}
                              </span>
                            </td>
                            <td className="px-3 py-2 text-xs text-muted-foreground">
                              {property.description && (
                                <p className="mb-1">{property.description}</p>
                              )}
                              <p className="text-muted-foreground/70 italic">
                                {example}
                              </p>
                              {property.enum && (
                                <p className="mt-1 text-[10px]">
                                  Options: {property.enum.join(", ")}
                                </p>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <p className="text-xs text-muted-foreground italic">
                No parameters required
              </p>
            )}
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
};

export default ToolCard;
