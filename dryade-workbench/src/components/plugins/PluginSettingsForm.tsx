// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useEffect, useMemo, useState } from "react";
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
import { Save } from "lucide-react";

// ---------------------------------------------------------------------------
// JSON Schema types (subset relevant to plugin settings)
// ---------------------------------------------------------------------------

interface JSONSchemaProperty {
  type: "string" | "number" | "integer" | "boolean";
  title?: string;
  description?: string;
  enum?: string[];
  default?: unknown;
  minimum?: number;
  maximum?: number;
}

interface JSONSchema {
  type: "object";
  properties: Record<string, JSONSchemaProperty>;
  required?: string[];
}

interface PluginSettingsFormProps {
  pluginName: string;
  schema: JSONSchema;
  config: Record<string, unknown>;
  onSave: (config: Record<string, unknown>) => void;
  isSaving?: boolean;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function initFormValues(
  schema: JSONSchema,
  config: Record<string, unknown>,
): Record<string, unknown> {
  const values: Record<string, unknown> = {};
  for (const [key, prop] of Object.entries(schema.properties)) {
    if (key in config && config[key] !== undefined) {
      values[key] = config[key];
    } else if (prop.default !== undefined) {
      values[key] = prop.default;
    } else {
      // Sensible empty defaults per type
      switch (prop.type) {
        case "string":
          values[key] = prop.enum ? prop.enum[0] ?? "" : "";
          break;
        case "number":
        case "integer":
          values[key] = prop.minimum ?? 0;
          break;
        case "boolean":
          values[key] = false;
          break;
      }
    }
  }
  return values;
}

function deepEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (typeof a !== typeof b) return false;
  if (typeof a !== "object" || a === null || b === null) return false;
  const keysA = Object.keys(a as Record<string, unknown>);
  const keysB = Object.keys(b as Record<string, unknown>);
  if (keysA.length !== keysB.length) return false;
  return keysA.every((k) =>
    deepEqual(
      (a as Record<string, unknown>)[k],
      (b as Record<string, unknown>)[k],
    ),
  );
}

// ---------------------------------------------------------------------------
// Field renderers
// ---------------------------------------------------------------------------

function StringEnumField({
  fieldKey,
  prop,
  value,
  onChange,
}: {
  fieldKey: string;
  prop: JSONSchemaProperty;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger id={fieldKey} className="w-full">
        <SelectValue placeholder="Select..." />
      </SelectTrigger>
      <SelectContent>
        {prop.enum!.map((opt) => (
          <SelectItem key={opt} value={opt}>
            {opt}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function StringField({
  fieldKey,
  value,
  onChange,
}: {
  fieldKey: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <Input
      id={fieldKey}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full"
    />
  );
}

function NumberSliderField({
  fieldKey,
  prop,
  value,
  onChange,
}: {
  fieldKey: string;
  prop: JSONSchemaProperty;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="flex items-center gap-3">
      <Slider
        id={fieldKey}
        value={[value]}
        min={prop.minimum}
        max={prop.maximum}
        step={prop.type === "integer" ? 1 : 0.01}
        onValueChange={([v]) => onChange(v)}
        className="flex-1"
      />
      <span className="text-sm text-muted-foreground tabular-nums w-12 text-right">
        {value}
      </span>
    </div>
  );
}

function NumberInputField({
  fieldKey,
  prop,
  value,
  onChange,
}: {
  fieldKey: string;
  prop: JSONSchemaProperty;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <Input
      id={fieldKey}
      type="number"
      step={prop.type === "integer" ? "1" : "0.01"}
      min={prop.minimum}
      max={prop.maximum}
      value={value}
      onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
      className="w-full"
    />
  );
}

function BooleanField({
  fieldKey,
  value,
  onChange,
}: {
  fieldKey: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return <Switch id={fieldKey} checked={value} onCheckedChange={onChange} />;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function PluginSettingsForm({
  pluginName: _pluginName,
  schema,
  config,
  onSave,
  isSaving = false,
}: PluginSettingsFormProps) {
  const initialValues = useMemo(() => initFormValues(schema, config), [schema, config]);
  const [values, setValues] = useState<Record<string, unknown>>(initialValues);

  // Re-sync when config changes externally (e.g. after save)
  useEffect(() => {
    setValues(initFormValues(schema, config));
  }, [schema, config]);

  const hasChanges = !deepEqual(values, initialValues);
  const requiredSet = useMemo(
    () => new Set(schema.required ?? []),
    [schema.required],
  );

  const updateField = (key: string, value: unknown) => {
    setValues((prev) => ({ ...prev, [key]: value }));
  };

  const handleSave = () => {
    onSave(values);
  };

  const entries = Object.entries(schema.properties);

  if (entries.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No configurable settings for this plugin.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      {entries.map(([key, prop]) => {
        const isRequired = requiredSet.has(key);
        const fieldValue = values[key];
        const label = prop.title ?? key.replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

        return (
          <div key={key} className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label htmlFor={key} className="text-sm">
                {label}
                {isRequired && <span className="text-destructive ml-0.5">*</span>}
              </Label>
              {prop.type === "boolean" && (
                <BooleanField
                  fieldKey={key}
                  value={Boolean(fieldValue)}
                  onChange={(v) => updateField(key, v)}
                />
              )}
            </div>

            {prop.description && (
              <p className="text-xs text-muted-foreground">{prop.description}</p>
            )}

            {/* String with enum -> Select */}
            {prop.type === "string" && prop.enum && (
              <StringEnumField
                fieldKey={key}
                prop={prop}
                value={String(fieldValue ?? "")}
                onChange={(v) => updateField(key, v)}
              />
            )}

            {/* String without enum -> Input */}
            {prop.type === "string" && !prop.enum && (
              <StringField
                fieldKey={key}
                value={String(fieldValue ?? "")}
                onChange={(v) => updateField(key, v)}
              />
            )}

            {/* Number/Integer with range -> Slider */}
            {(prop.type === "number" || prop.type === "integer") &&
              prop.minimum !== undefined &&
              prop.maximum !== undefined && (
                <NumberSliderField
                  fieldKey={key}
                  prop={prop}
                  value={Number(fieldValue ?? 0)}
                  onChange={(v) => updateField(key, v)}
                />
              )}

            {/* Number/Integer without range -> Number input */}
            {(prop.type === "number" || prop.type === "integer") &&
              (prop.minimum === undefined || prop.maximum === undefined) && (
                <NumberInputField
                  fieldKey={key}
                  prop={prop}
                  value={Number(fieldValue ?? 0)}
                  onChange={(v) => updateField(key, v)}
                />
              )}

            {/* Boolean is rendered inline with the label above */}
          </div>
        );
      })}

      <div className="pt-2">
        <Button
          size="sm"
          disabled={isSaving || !hasChanges}
          onClick={handleSave}
        >
          <Save className="w-4 h-4 mr-2" />
          {isSaving ? "Saving..." : "Save Settings"}
        </Button>
      </div>
    </div>
  );
}
