// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMemo, useState } from "react";
import type { ScenarioInputSchema } from "@/types/extended-api";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { FileUploadField } from "./FileUploadField";

interface WorkflowInputFormProps {
  inputs: ScenarioInputSchema[];
  onSubmit: (values: Record<string, unknown>, files: Record<string, File>) => void;
  onCancel?: () => void;
  isLoading?: boolean;
}

// Build zod schema dynamically from input definitions
const buildSchema = (inputs: ScenarioInputSchema[]) => {
  const shape: Record<string, z.ZodTypeAny> = {};
  for (const input of inputs) {
    // Skip file inputs - they're handled separately
    if (input.type === "file") continue;

    let field: z.ZodTypeAny;
    switch (input.type) {
      case "number":
        field = z.coerce.number();
        break;
      case "boolean":
        field = z.boolean();
        break;
      case "json":
        field = z.string().refine(
          (val) => {
            if (!val || val.trim() === "") return true;
            try {
              JSON.parse(val);
              return true;
            } catch {
              return false;
            }
          },
          { message: "Must be valid JSON" }
        );
        break;
      default:
        field = z.string();
    }
    if (!input.required) {
      field = field.optional();
    } else if (input.type === "string" || input.type === "json") {
      // Add min length validation for required string fields
      field = z.string().min(1, "This field is required");
      if (input.type === "json") {
        field = z
          .string()
          .min(1, "This field is required")
          .refine(
            (val) => {
              try {
                JSON.parse(val);
                return true;
              } catch {
                return false;
              }
            },
            { message: "Must be valid JSON" }
          );
      }
    }
    shape[input.name] = field;
  }
  return z.object(shape);
};

// Build default values from input definitions
const buildDefaults = (inputs: ScenarioInputSchema[]) => {
  const defaults: Record<string, unknown> = {};
  for (const input of inputs) {
    // Skip file inputs - they're handled separately
    if (input.type === "file") continue;

    if (input.default !== undefined) {
      if (input.type === "json") {
        defaults[input.name] =
          typeof input.default === "string"
            ? input.default
            : JSON.stringify(input.default, null, 2);
      } else {
        defaults[input.name] = input.default;
      }
    } else if (input.type === "boolean") {
      defaults[input.name] = false;
    } else {
      defaults[input.name] = "";
    }
  }
  return defaults;
};

// Transform form values before submission (parse JSON strings)
const transformValues = (
  values: Record<string, unknown>,
  inputs: ScenarioInputSchema[]
): Record<string, unknown> => {
  const result: Record<string, unknown> = {};
  for (const input of inputs) {
    // Skip file inputs - they're handled separately
    if (input.type === "file") continue;

    const value = values[input.name];
    if (input.type === "json" && typeof value === "string" && value.trim()) {
      try {
        result[input.name] = JSON.parse(value);
      } catch {
        result[input.name] = value;
      }
    } else if (value !== undefined && value !== "") {
      result[input.name] = value;
    }
  }
  return result;
};

export const WorkflowInputForm = ({
  inputs,
  onSubmit,
  onCancel,
  isLoading = false,
}: WorkflowInputFormProps) => {
  const schema = useMemo(() => buildSchema(inputs), [inputs]);
  const defaults = useMemo(() => buildDefaults(inputs), [inputs]);

  // Separate state for file inputs (not managed by react-hook-form)
  const [fileInputs, setFileInputs] = useState<Record<string, File | null>>({});
  const [fileErrors, setFileErrors] = useState<Record<string, string>>({});

  const {
    register,
    handleSubmit,
    formState: { errors },
    setValue,
    watch,
  } = useForm({
    resolver: zodResolver(schema),
    defaultValues: defaults,
  });

  // Get list of file inputs for validation
  const fileInputDefs = useMemo(
    () => inputs.filter((input) => input.type === "file"),
    [inputs]
  );

  const handleFileChange = (name: string, file: File | null) => {
    setFileInputs((prev) => ({ ...prev, [name]: file }));
    // Clear error when file is selected
    if (file) {
      setFileErrors((prev) => {
        const next = { ...prev };
        delete next[name];
        return next;
      });
    }
  };

  const validateFiles = (): boolean => {
    const newErrors: Record<string, string> = {};
    for (const input of fileInputDefs) {
      if (input.required && !fileInputs[input.name]) {
        newErrors[input.name] = "This file is required";
      }
    }
    setFileErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleFormSubmit = (values: Record<string, unknown>) => {
    // Validate file inputs
    if (!validateFiles()) {
      return;
    }

    const transformed = transformValues(values, inputs);

    // Collect non-null files
    const files: Record<string, File> = {};
    for (const [name, file] of Object.entries(fileInputs)) {
      if (file) {
        files[name] = file;
      }
    }

    onSubmit(transformed, files);
  };

  const renderField = (input: ScenarioInputSchema) => {
    const error = errors[input.name];
    const fieldId = `input-${input.name}`;

    const labelElement = (
      <>
        <Label htmlFor={fieldId} className="text-sm font-medium">
          {input.name
            .replace(/_/g, " ")
            .replace(/\b\w/g, (c) => c.toUpperCase())}
          {input.required && <span className="text-destructive ml-1">*</span>}
        </Label>
        {input.description && (
          <p className="text-xs text-muted-foreground">{input.description}</p>
        )}
      </>
    );

    // Handle file inputs with dedicated component
    if (input.type === "file") {
      const fileError = fileErrors[input.name];
      return (
        <div key={input.name} className="space-y-2">
          {labelElement}
          <FileUploadField
            id={fieldId}
            value={fileInputs[input.name] || null}
            onChange={(file) => handleFileChange(input.name, file)}
            disabled={isLoading}
            error={!!fileError}
          />
          {fileError && (
            <p className="text-xs text-destructive">{fileError}</p>
          )}
        </div>
      );
    }

    return (
      <div key={input.name} className="space-y-2">
        {labelElement}

        {input.type === "boolean" ? (
          <div className="flex items-center gap-2">
            <Switch
              id={fieldId}
              checked={watch(input.name) as boolean}
              onCheckedChange={(checked) => setValue(input.name, checked)}
              disabled={isLoading}
            />
            <span className="text-sm text-muted-foreground">
              {watch(input.name) ? "Yes" : "No"}
            </span>
          </div>
        ) : input.type === "json" ? (
          <Textarea
            id={fieldId}
            {...register(input.name)}
            placeholder='{"key": "value"}'
            className={cn("font-mono text-sm", error && "border-destructive")}
            rows={4}
            disabled={isLoading}
          />
        ) : input.type === "number" ? (
          <Input
            id={fieldId}
            type="number"
            {...register(input.name)}
            className={cn(error && "border-destructive")}
            disabled={isLoading}
          />
        ) : (
          <Input
            id={fieldId}
            type="text"
            {...register(input.name)}
            placeholder={input.default ? String(input.default) : undefined}
            className={cn(error && "border-destructive")}
            disabled={isLoading}
          />
        )}

        {error && (
          <p className="text-xs text-destructive">{error.message as string}</p>
        )}
      </div>
    );
  };

  if (inputs.length === 0) {
    return (
      <div className="text-center py-6 text-muted-foreground">
        <p className="text-sm">This workflow has no required inputs.</p>
        <div className="flex gap-2 pt-4 mt-4 border-t border-border">
          {onCancel && (
            <Button
              type="button"
              variant="outline"
              onClick={onCancel}
              disabled={isLoading}
              className="flex-1"
            >
              Cancel
            </Button>
          )}
          <Button
            type="button"
            onClick={() => onSubmit({}, {})}
            disabled={isLoading}
            className="flex-1"
          >
            {isLoading ? "Running..." : "Run Workflow"}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit(handleFormSubmit)} className="space-y-4">
      {inputs.map(renderField)}

      <div className="flex gap-2 pt-4 border-t border-border">
        {onCancel && (
          <Button
            type="button"
            variant="outline"
            onClick={onCancel}
            disabled={isLoading}
            className="flex-1"
          >
            Cancel
          </Button>
        )}
        <Button type="submit" disabled={isLoading} className="flex-1">
          {isLoading ? "Running..." : "Run Workflow"}
        </Button>
      </div>
    </form>
  );
};

export default WorkflowInputForm;
