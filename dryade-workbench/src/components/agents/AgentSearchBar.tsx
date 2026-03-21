// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useEffect } from "react";
import { Search, X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

interface AgentSearchBarProps {
  onSearch: (query: string) => void;
  placeholder?: string;
}

const AgentSearchBar = ({ onSearch, placeholder = "Search agents by name or description..." }: AgentSearchBarProps) => {
  const [value, setValue] = useState("");

  // Debounced search
  useEffect(() => {
    const timer = setTimeout(() => {
      onSearch(value);
    }, 300);
    return () => clearTimeout(timer);
  }, [value, onSearch]);

  const handleClear = () => {
    setValue("");
    onSearch("");
  };

  return (
    <div className="relative">
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
      <Input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={placeholder}
        className="pl-10 pr-10 bg-secondary/50"
        aria-label="Search agents"
      />
      {value && (
        <Button
          variant="ghost"
          size="icon"
          onClick={handleClear}
          className="absolute right-1 top-1/2 -translate-y-1/2 h-7 w-7"
          aria-label="Clear search"
        >
          <X size={14} />
        </Button>
      )}
    </div>
  );
};

export default AgentSearchBar;
