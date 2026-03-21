// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { cn } from "@/lib/utils";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Star, Sparkles, Bot } from "lucide-react";
import type { Model } from "@/types/extended-api";

type RoutingMode = "auto" | "default" | "specific";

interface ModelSelectorProps {
  models: Model[];
  value: string;
  onChange: (value: string) => void;
  routingMode?: RoutingMode;
  onRoutingModeChange?: (mode: RoutingMode) => void;
  disabled?: boolean;
  className?: string;
}

const ModelSelector = ({
  models,
  value,
  onChange,
  routingMode = "auto",
  onRoutingModeChange,
  disabled = false,
  className,
}: ModelSelectorProps) => {
  const defaultModel = models.find((m) => m.is_default);
  const availableModels = models.filter((m) => m.status === "available");

  const handleValueChange = (newValue: string) => {
    if (newValue === "__auto__") {
      onRoutingModeChange?.("auto");
      onChange("");
    } else if (newValue === "__default__") {
      onRoutingModeChange?.("default");
      onChange(defaultModel?.id || "");
    } else {
      onRoutingModeChange?.("specific");
      onChange(newValue);
    }
  };

  const getCurrentValue = () => {
    if (routingMode === "auto") return "__auto__";
    if (routingMode === "default") return "__default__";
    return value;
  };

  const getDisplayValue = () => {
    if (routingMode === "auto") return "Auto-select";
    if (routingMode === "default") return defaultModel?.display_name || "Default";
    const selected = models.find((m) => m.id === value);
    return selected?.display_name || "Select model";
  };

  return (
    <Select
      value={getCurrentValue()}
      onValueChange={handleValueChange}
      disabled={disabled}
    >
      <SelectTrigger className={cn("w-full", className)}>
        <SelectValue>{getDisplayValue()}</SelectValue>
      </SelectTrigger>
      <SelectContent>
        {/* Auto option */}
        <SelectItem value="__auto__">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-primary" />
            <span>Auto-select</span>
            <Badge variant="secondary" className="ml-2 text-xs">
              Recommended
            </Badge>
          </div>
        </SelectItem>

        {/* Default model option */}
        {defaultModel && (
          <SelectItem value="__default__">
            <div className="flex items-center gap-2">
              <Star className="w-4 h-4 text-warning" />
              <span>Use Default ({defaultModel.display_name})</span>
            </div>
          </SelectItem>
        )}

        {/* Separator */}
        <div className="my-1 border-t border-border" />

        {/* Specific models */}
        {availableModels.map((model) => (
          <SelectItem key={model.id} value={model.id}>
            <div className="flex items-center gap-2">
              <Bot className="w-4 h-4 text-muted-foreground" />
              <span>{model.display_name}</span>
              {model.is_custom && (
                <Badge variant="outline" className="ml-2 text-xs">
                  Custom
                </Badge>
              )}
              {model.is_default && (
                <Star className="w-3 h-3 text-warning fill-warning ml-1" />
              )}
            </div>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
};

export default ModelSelector;
