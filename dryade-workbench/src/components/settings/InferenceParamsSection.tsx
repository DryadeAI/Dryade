// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
/**
 * InferenceParamsSection - Slider + number-field controls for inference parameters.
 * Supports preset dropdown, provider-aware visibility, vLLM advanced params, and reset.
 */
import { useState, useCallback, useMemo } from "react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Slider } from "@/components/ui/slider";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { ChevronDown, RotateCcw, X } from "lucide-react";
import type { ModelCapability, ParamSpec, InferenceParams } from "@/types/extended-api";

/** Consistent display order for parameters */
const PARAM_ORDER = [
  "temperature", "top_p", "top_k", "max_tokens",
  "repetition_penalty", "frequency_penalty", "presence_penalty",
  "timeout", "planner_timeout",
];

interface InferenceParamsSectionProps {
  capability: ModelCapability;
  provider: string;
  params: InferenceParams;
  supportedParams: string[];
  paramSpecs: Record<string, ParamSpec>;
  presets: Record<string, Record<string, number>>;
  vllmServerParams?: InferenceParams;
  vllmServerParamSpecs?: Record<string, ParamSpec>;
  onParamsChange: (params: InferenceParams) => void;
  onVllmServerParamsChange?: (params: InferenceParams) => void;
  onReset: () => void;
}

/** Derive current preset name by comparing params to each preset */
function detectPreset(
  params: InferenceParams,
  presets: Record<string, Record<string, number>>,
  supportedParams: string[]
): string {
  for (const [presetName, presetValues] of Object.entries(presets)) {
    const matches = Object.entries(presetValues).every(([key, value]) => {
      if (!supportedParams.includes(key)) return true;
      const current = params[key];
      if (current === undefined) return value === undefined;
      return Number(current) === value;
    });
    if (matches) return presetName;
  }
  return "custom";
}

/** Format a numeric value for display, avoiding IEEE 754 noise */
function formatValue(value: number | string | string[], spec: ParamSpec): string {
  if (typeof value === "number") {
    if (spec.type === "float") return parseFloat(value.toFixed(2)).toString();
    return Math.round(value).toString();
  }
  return String(value);
}

export const InferenceParamsSection = (props: InferenceParamsSectionProps) => {
  const {
    provider, params, supportedParams, paramSpecs, presets,
    vllmServerParams, vllmServerParamSpecs,
    onParamsChange, onVllmServerParamsChange, onReset,
  } = props;

  const [stopInput, setStopInput] = useState("");

  // Order supported params according to PARAM_ORDER
  const orderedParams = useMemo(() => {
    const ordered: string[] = [];
    for (const name of PARAM_ORDER) {
      if (supportedParams.includes(name) && name !== "stop") ordered.push(name);
    }
    // Add any remaining supported params not in PARAM_ORDER
    for (const name of supportedParams) {
      if (!ordered.includes(name) && name !== "stop") ordered.push(name);
    }
    return ordered;
  }, [supportedParams]);

  const hasStop = supportedParams.includes("stop");
  const showVllmAdvanced = provider === "vllm" && vllmServerParamSpecs && Object.keys(vllmServerParamSpecs).length > 0;

  const currentPreset = useMemo(
    () => detectPreset(params, presets, supportedParams),
    [params, presets, supportedParams]
  );

  const handleParamChange = useCallback((name: string, value: number) => {
    onParamsChange({ ...params, [name]: value });
  }, [params, onParamsChange]);

  const handleInputChange = useCallback((name: string, rawValue: string, spec: ParamSpec) => {
    const parsed = parseFloat(rawValue);
    if (isNaN(parsed)) return;
    const min = spec.min ?? -Infinity;
    const max = spec.max ?? Infinity;
    const clamped = Math.min(max, Math.max(min, parsed));
    onParamsChange({ ...params, [name]: clamped });
  }, [params, onParamsChange]);

  const handlePresetSelect = useCallback((presetName: string) => {
    if (presetName === "custom") return;
    const presetValues = presets[presetName];
    if (!presetValues) return;
    // Merge preset values into current params (only override supported keys)
    const merged = { ...params };
    for (const [key, value] of Object.entries(presetValues)) {
      if (supportedParams.includes(key)) {
        merged[key] = value;
      }
    }
    onParamsChange(merged);
  }, [params, presets, supportedParams, onParamsChange]);

  const handleAddStop = useCallback(() => {
    const trimmed = stopInput.trim();
    if (!trimmed) return;
    const current = Array.isArray(params.stop) ? (params.stop as string[]) : [];
    if (!current.includes(trimmed)) {
      onParamsChange({ ...params, stop: [...current, trimmed] });
    }
    setStopInput("");
  }, [stopInput, params, onParamsChange]);

  const handleRemoveStop = useCallback((seq: string) => {
    const current = Array.isArray(params.stop) ? (params.stop as string[]) : [];
    onParamsChange({ ...params, stop: current.filter(s => s !== seq) });
  }, [params, onParamsChange]);

  const handleVllmParamChange = useCallback((name: string, value: number | string) => {
    if (!onVllmServerParamsChange || !vllmServerParams) return;
    onVllmServerParamsChange({ ...vllmServerParams, [name]: value });
  }, [vllmServerParams, onVllmServerParamsChange]);

  // If no params to show, render nothing
  if (orderedParams.length === 0 && !hasStop) return null;

  return (
    <Collapsible defaultOpen={false}>
      <CollapsibleTrigger className="flex items-center gap-2 text-sm font-medium cursor-pointer hover:text-primary w-full py-2">
        <ChevronDown className="h-4 w-4 transition-transform" />
        Inference Parameters
      </CollapsibleTrigger>
      <CollapsibleContent className="space-y-4 pt-2">
        {/* Preset dropdown */}
        {orderedParams.length > 0 && (
          <div className="flex items-center gap-3">
            <Label className="text-sm whitespace-nowrap">Preset</Label>
            <Select value={currentPreset} onValueChange={handlePresetSelect}>
              <SelectTrigger className="w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="precise">Precise</SelectItem>
                <SelectItem value="balanced">Balanced</SelectItem>
                <SelectItem value="creative">Creative</SelectItem>
                <SelectItem value="custom">Custom</SelectItem>
              </SelectContent>
            </Select>
          </div>
        )}

        {/* Parameter sliders */}
        <div className="space-y-3">
          {orderedParams.map(name => {
            const spec = paramSpecs[name];
            if (!spec) return null;
            const currentValue = params[name] ?? spec.default;
            const numValue = typeof currentValue === "number" ? currentValue : Number(currentValue);
            const min = spec.min ?? 0;
            const max = spec.max ?? 100;

            return (
              <div key={name} className="space-y-1">
                <div className="flex items-center justify-between">
                  <Label className="text-xs">{spec.label}</Label>
                  <Input
                    type="number"
                    min={min}
                    max={max}
                    step={spec.step}
                    value={formatValue(numValue, spec)}
                    onChange={(e) => handleInputChange(name, e.target.value, spec)}
                    className="w-20 h-7 text-xs text-right"
                  />
                </div>
                <Slider
                  min={min}
                  max={max}
                  step={spec.step}
                  value={[numValue]}
                  onValueChange={([v]) => handleParamChange(name, v)}
                />
                <p className="text-muted-foreground text-xs">{spec.description}</p>
              </div>
            );
          })}
        </div>

        {/* Stop sequences */}
        {hasStop && (
          <div className="space-y-2">
            <Label className="text-xs">Stop Sequences</Label>
            <div className="flex flex-wrap gap-1">
              {Array.isArray(params.stop) && (params.stop as string[]).map(seq => (
                <Badge key={seq} variant="secondary" className="text-xs gap-1">
                  {seq}
                  <button
                    onClick={() => handleRemoveStop(seq)}
                    className="hover:text-destructive"
                    aria-label={`Remove stop sequence ${seq}`}
                  >
                    <X className="h-3 w-3" />
                  </button>
                </Badge>
              ))}
            </div>
            <div className="flex gap-2">
              <Input
                value={stopInput}
                onChange={(e) => setStopInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); handleAddStop(); } }}
                placeholder="Add stop sequence..."
                className="h-7 text-xs flex-1"
              />
              <Button variant="outline" size="sm" onClick={handleAddStop} className="h-7 text-xs">
                Add
              </Button>
            </div>
          </div>
        )}

        {/* vLLM Advanced Parameters */}
        {showVllmAdvanced && vllmServerParamSpecs && (
          <Collapsible defaultOpen={false}>
            <CollapsibleTrigger className="flex items-center gap-2 text-sm font-medium cursor-pointer hover:text-primary w-full py-2">
              <ChevronDown className="h-4 w-4 transition-transform" />
              Advanced Parameters
              <Badge variant="outline" className="text-xs text-amber-500">Requires vLLM restart</Badge>
            </CollapsibleTrigger>
            <CollapsibleContent className="space-y-3 pt-2">
              {Object.entries(vllmServerParamSpecs).map(([name, spec]) => {
                const currentValue = vllmServerParams?.[name] ?? spec.default;

                // Enum type: render a select dropdown
                if (spec.type === "enum") {
                  const enumOptions = name === "dtype"
                    ? ["auto", "float16", "bfloat16", "float32"]
                    : [String(spec.default)];
                  return (
                    <div key={name} className="space-y-1">
                      <div className="flex items-center justify-between">
                        <Label className="text-xs">{spec.label}</Label>
                        <Select
                          value={String(currentValue)}
                          onValueChange={(v) => handleVllmParamChange(name, v)}
                        >
                          <SelectTrigger className="w-32 h-7 text-xs">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {enumOptions.map(opt => (
                              <SelectItem key={opt} value={opt}>{opt}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <p className="text-muted-foreground text-xs">{spec.description}</p>
                    </div>
                  );
                }

                // Numeric type: slider + input
                const numValue = typeof currentValue === "number" ? currentValue : Number(currentValue);
                const min = spec.min ?? 0;
                const max = spec.max ?? 100;
                return (
                  <div key={name} className="space-y-1">
                    <div className="flex items-center justify-between">
                      <Label className="text-xs">{spec.label}</Label>
                      <Input
                        type="number"
                        min={min}
                        max={max}
                        step={spec.step}
                        value={formatValue(numValue, spec)}
                        onChange={(e) => {
                          const parsed = parseFloat(e.target.value);
                          if (!isNaN(parsed)) {
                            handleVllmParamChange(name, Math.min(max, Math.max(min, parsed)));
                          }
                        }}
                        className="w-20 h-7 text-xs text-right"
                      />
                    </div>
                    <Slider
                      min={min}
                      max={max}
                      step={spec.step}
                      value={[numValue]}
                      onValueChange={([v]) => handleVllmParamChange(name, v)}
                    />
                    <p className="text-muted-foreground text-xs">{spec.description}</p>
                  </div>
                );
              })}
            </CollapsibleContent>
          </Collapsible>
        )}

        {/* Reset to Defaults */}
        <div className="pt-2">
          <Button variant="outline" size="sm" onClick={onReset} className="gap-1.5">
            <RotateCcw className="h-3.5 w-3.5" />
            Reset to Defaults
          </Button>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
};
