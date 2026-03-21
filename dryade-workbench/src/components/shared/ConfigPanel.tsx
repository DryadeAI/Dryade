// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// ConfigPanel - Generic configuration form
// Based on COMPONENTS-4.md specification

import React, { useState, useEffect } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { AlertTriangle, Save, RotateCcw, Loader2, Check } from "lucide-react";

interface ConfigField {
  key: string;
  label: string;
  type: "toggle" | "slider" | "number" | "select" | "text";
  min?: number;
  max?: number;
  step?: number;
  options?: Array<{ value: string; label: string }>;
  description?: string;
  placeholder?: string;
}

interface ConfigPanelProps {
  title: string;
  description?: string;
  config: Record<string, unknown>;
  schema: ConfigField[];
  onSave: (updates: Record<string, unknown>) => Promise<void>;
  onReset?: () => void;
  warning?: string;
  loading?: boolean;
  className?: string;
}

type ConfigState = "clean" | "dirty" | "saving" | "saved" | "error";

const ConfigPanel = ({
  title,
  description,
  config,
  schema,
  onSave,
  onReset,
  warning,
  loading = false,
  className,
}: ConfigPanelProps) => {
  const [localConfig, setLocalConfig] = useState<Record<string, unknown>>(config);
  const [state, setState] = useState<ConfigState>("clean");
  const [error, setError] = useState<string | null>(null);

  // Sync external config changes
  useEffect(() => {
    setLocalConfig(config);
    setState("clean");
  }, [config]);

  const handleChange = (key: string, value: unknown) => {
    setLocalConfig((prev) => ({ ...prev, [key]: value }));
    setState("dirty");
    setError(null);
  };

  const handleSave = async () => {
    setState("saving");
    setError(null);

    try {
      await onSave(localConfig);
      setState("saved");
      setTimeout(() => setState("clean"), 2000);
    } catch (err) {
      setState("error");
      setError(err instanceof Error ? err.message : "Failed to save");
    }
  };

  const handleReset = () => {
    setLocalConfig(config);
    setState("clean");
    setError(null);
    onReset?.();
  };

  const isDirty = state === "dirty" || Object.keys(config).some(
    (key) => config[key] !== localConfig[key]
  );

  const renderField = (field: ConfigField): React.ReactNode => {
    const value = localConfig[field.key];

    switch (field.type) {
      case "toggle":
        return (
          <div className="flex items-center justify-between gap-4 p-3 rounded-lg bg-muted/30">
            <div>
              <Label htmlFor={field.key} className="text-sm font-medium cursor-pointer">
                {field.label}
              </Label>
              {field.description && (
                <p className="text-xs text-muted-foreground mt-0.5">{field.description}</p>
              )}
            </div>
            <Switch
              id={field.key}
              checked={!!value}
              onCheckedChange={(checked) => handleChange(field.key, checked)}
              disabled={loading}
            />
          </div>
        );

      case "slider":
        return (
          <div className="space-y-2 p-3 rounded-lg bg-muted/30">
            <div className="flex items-center justify-between">
              <Label htmlFor={field.key} className="text-sm font-medium">
                {field.label}
              </Label>
              <span className="text-xs font-mono text-muted-foreground">
                {typeof value === "number" ? value.toFixed(2) : String(value ?? "")}
              </span>
            </div>
            {field.description && (
              <p className="text-xs text-muted-foreground">{field.description}</p>
            )}
            <Slider
              id={field.key}
              value={[typeof value === "number" ? value : field.min || 0]}
              onValueChange={([val]) => handleChange(field.key, val)}
              min={field.min ?? 0}
              max={field.max ?? 100}
              step={field.step ?? 1}
              disabled={loading}
            />
          </div>
        );

      case "number":
        return (
          <div className="space-y-2 p-3 rounded-lg bg-muted/30">
            <Label htmlFor={field.key} className="text-sm font-medium">
              {field.label}
            </Label>
            {field.description && (
              <p className="text-xs text-muted-foreground">{field.description}</p>
            )}
            <Input
              id={field.key}
              type="number"
              value={typeof value === "number" ? value : ""}
              onChange={(e) => handleChange(field.key, parseFloat(e.target.value) || 0)}
              min={field.min}
              max={field.max}
              step={field.step}
              disabled={loading}
              placeholder={field.placeholder}
            />
          </div>
        );

      case "select":
        return (
          <div className="space-y-2 p-3 rounded-lg bg-muted/30">
            <Label htmlFor={field.key} className="text-sm font-medium">
              {field.label}
            </Label>
            {field.description && (
              <p className="text-xs text-muted-foreground">{field.description}</p>
            )}
            <Select
              value={String(value || "")}
              onValueChange={(val) => handleChange(field.key, val)}
              disabled={loading}
            >
              <SelectTrigger id={field.key}>
                <SelectValue placeholder={field.placeholder || "Select..."} />
              </SelectTrigger>
              <SelectContent>
                {field.options?.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        );

      case "text":
        return (
          <div className="space-y-2 p-3 rounded-lg bg-muted/30">
            <Label htmlFor={field.key} className="text-sm font-medium">
              {field.label}
            </Label>
            {field.description && (
              <p className="text-xs text-muted-foreground">{field.description}</p>
            )}
            <Input
              id={field.key}
              value={String(value || "")}
              onChange={(e) => handleChange(field.key, e.target.value)}
              disabled={loading}
              placeholder={field.placeholder}
            />
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <Card className={cn("overflow-hidden", className)}>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div>
            <CardTitle className="text-lg">{title}</CardTitle>
            {description && (
              <CardDescription className="mt-1">{description}</CardDescription>
            )}
          </div>
          {/* State indicator */}
          {state === "saved" && (
            <span className="flex items-center gap-1 text-xs text-success">
              <Check className="w-3 h-3" /> Saved
            </span>
          )}
        </div>

        {/* Warning */}
        {warning && (
          <div className="flex items-center gap-2 p-2 rounded-lg bg-amber-500/10 text-amber-600 text-xs mt-2">
            <AlertTriangle className="w-4 h-4 flex-shrink-0" />
            {warning}
          </div>
        )}
      </CardHeader>

      <CardContent className="space-y-3">
        {/* Fields */}
        {schema.map((field) => (
          <div key={field.key}>{renderField(field)}</div>
        ))}

        {/* Error */}
        {error && (
          <p className="text-sm text-destructive">{error}</p>
        )}

        {/* Actions */}
        <div className="flex items-center gap-2 pt-2">
          <Button
            onClick={handleSave}
            disabled={loading || !isDirty || state === "saving"}
            className="flex-1"
          >
            {state === "saving" ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Save className="w-4 h-4 mr-2" />
                Save Changes
              </>
            )}
          </Button>
          {onReset && (
            <Button
              variant="outline"
              onClick={handleReset}
              disabled={loading || !isDirty}
            >
              <RotateCcw className="w-4 h-4" />
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
};

export default ConfigPanel;
