// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// SearchInput - Knowledge search with threshold slider
// Based on COMPONENTS-4.md specification

import { useState, useEffect, useCallback } from "react";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Search, X, Loader2 } from "lucide-react";

interface SearchInputProps {
  placeholder?: string;
  value: string;
  onChange: (query: string) => void;
  threshold: number;
  onThresholdChange: (value: number) => void;
  onSearch?: () => void;
  debounceMs?: number;
  disabled?: boolean;
  loading?: boolean;
  showThreshold?: boolean;
  className?: string;
}

const SearchInput = ({
  placeholder = "Search...",
  value,
  onChange,
  threshold,
  onThresholdChange,
  onSearch,
  debounceMs = 300,
  disabled = false,
  loading = false,
  showThreshold = true,
  className,
}: SearchInputProps) => {
  const [localValue, setLocalValue] = useState(value);

  // Debounce input changes
  useEffect(() => {
    const timer = setTimeout(() => {
      if (localValue !== value) {
        onChange(localValue);
      }
    }, debounceMs);

    return () => clearTimeout(timer);
  }, [localValue, debounceMs, onChange, value]);

  // Sync external value changes
  useEffect(() => {
    setLocalValue(value);
  }, [value]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === "Enter" && onSearch) {
      onSearch();
    }
    if (e.key === "Escape") {
      setLocalValue("");
      onChange("");
    }
  }, [onSearch, onChange]);

  const handleClear = () => {
    setLocalValue("");
    onChange("");
  };

  const getThresholdLabel = (val: number): string => {
    if (val >= 0.9) return "Strict";
    if (val >= 0.7) return "Normal";
    if (val >= 0.5) return "Loose";
    return "Very Loose";
  };

  return (
    <div className={cn("space-y-3", className)}>
      {/* Search Input */}
      <div className="relative">
        <Search
          className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none"
        />
        <Input
          value={localValue}
          onChange={(e) => setLocalValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          className="pl-9 pr-16"
          aria-label="Search input"
          aria-describedby={showThreshold ? "threshold-description" : undefined}
        />
        <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1">
          {loading && (
            <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
          )}
          {localValue && !loading && (
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              onClick={handleClear}
              aria-label="Clear search"
            >
              <X className="w-3 h-3" />
            </Button>
          )}
          {onSearch && (
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              onClick={onSearch}
              disabled={disabled || !localValue.trim()}
              aria-label="Submit search"
            >
              <Search className="w-3 h-3" />
            </Button>
          )}
        </div>
      </div>

      {/* Threshold Slider */}
      {showThreshold && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label
              htmlFor="threshold-slider"
              className="text-xs text-muted-foreground"
            >
              Similarity Threshold
            </Label>
            <span className="text-xs font-medium">
              {threshold.toFixed(2)} ({getThresholdLabel(threshold)})
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-muted-foreground">Loose</span>
            <Slider
              id="threshold-slider"
              value={[threshold]}
              onValueChange={([val]) => onThresholdChange(val)}
              min={0}
              max={1}
              step={0.05}
              disabled={disabled}
              className="flex-1"
              aria-describedby="threshold-description"
            />
            <span className="text-[10px] text-muted-foreground">Strict</span>
          </div>
          <p id="threshold-description" className="sr-only">
            Adjust similarity threshold from 0 (loose) to 1 (strict)
          </p>
        </div>
      )}
    </div>
  );
};

export default SearchInput;
