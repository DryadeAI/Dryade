// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// McpStep -- MCP server configuration (OPTIONAL step)
// Shows detected MCP servers with checkboxes, or a message if none found

import { useState } from "react";
import type { StepProps } from "../OnboardingWizard";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Server, ExternalLink } from "lucide-react";

// Placeholder -- in a real implementation this would call GET /api/mcp/servers
const COMMON_MCP_SERVERS = [
  { id: "filesystem", name: "Filesystem", description: "Read and write files on your machine" },
  { id: "brave-search", name: "Brave Search", description: "Web search via Brave Search API" },
  { id: "github", name: "GitHub", description: "Repository management and code search" },
  { id: "memory", name: "Memory", description: "Persistent knowledge graph for agents" },
];

const McpStep = ({ data, onUpdate }: StepProps) => {
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const toggleServer = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    setSelected(next);

    const serverMap: Record<string, unknown> = {};
    next.forEach((s) => {
      serverMap[s] = { enabled: true };
    });
    onUpdate({ mcpServers: serverMap });
  };

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">MCP Servers</h2>
        <p className="text-sm text-muted-foreground">
          MCP servers give your agents access to external tools and data sources.
        </p>
      </div>

      <div className="space-y-2">
        {COMMON_MCP_SERVERS.map((server) => (
          <Label
            key={server.id}
            htmlFor={`mcp-${server.id}`}
            className="flex cursor-pointer items-center gap-3 rounded-lg border border-border p-3 transition-colors hover:bg-muted/50"
          >
            <Checkbox
              id={`mcp-${server.id}`}
              checked={selected.has(server.id)}
              onCheckedChange={() => toggleServer(server.id)}
            />
            <Server className="h-4 w-4 text-muted-foreground" />
            <div className="flex-1">
              <span className="text-sm font-medium">{server.name}</span>
              <p className="text-xs text-muted-foreground">{server.description}</p>
            </div>
          </Label>
        ))}
      </div>

      <div className="rounded-md border border-border/50 bg-muted/30 p-3">
        <p className="text-xs text-muted-foreground">
          <ExternalLink className="mb-0.5 mr-1 inline h-3 w-3" />
          MCP servers are configured in your <code className="text-foreground">mcp.json</code> file.
          You can add or change servers anytime from Settings.
        </p>
      </div>
    </div>
  );
};

export default McpStep;
