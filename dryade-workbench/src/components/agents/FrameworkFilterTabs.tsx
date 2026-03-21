// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { cn } from "@/lib/utils";
import type { AgentFramework } from "@/types/api";

type FilterValue = AgentFramework | "all";

interface FrameworkFilterTabsProps {
  activeFilter: FilterValue;
  onFilterChange: (filter: FilterValue) => void;
  counts: Record<FilterValue, number>;
}

const tabs: { value: FilterValue; label: string }[] = [
  { value: "all", label: "All" },
  { value: "crewai", label: "CrewAI" },
  { value: "langchain", label: "LangChain" },
  { value: "adk", label: "ADK" },
  { value: "a2a", label: "A2A" },
  { value: "mcp", label: "MCP" },
  { value: "custom", label: "Custom" },
];

const FrameworkFilterTabs = ({ activeFilter, onFilterChange, counts }: FrameworkFilterTabsProps) => {
  return (
    <div 
      role="tablist" 
      aria-label="Filter agents by framework"
      className="flex gap-1 p-1 bg-secondary/50 rounded-lg overflow-x-auto"
    >
      {tabs.map((tab) => (
        <button
          key={tab.value}
          role="tab"
          aria-selected={activeFilter === tab.value}
          onClick={() => onFilterChange(tab.value)}
          className={cn(
            "px-3 py-1.5 rounded-md text-sm font-medium transition-colors whitespace-nowrap",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            activeFilter === tab.value
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground hover:bg-background/50"
          )}
        >
          {tab.label}
          <span className="ml-1.5 text-xs opacity-60">
            {counts[tab.value] || 0}
          </span>
        </button>
      ))}
    </div>
  );
};

export default FrameworkFilterTabs;
