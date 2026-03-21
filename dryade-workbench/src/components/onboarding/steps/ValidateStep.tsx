// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// ValidateStep -- connection validation (REQUIRED step)
// Auto-validates on mount, shows success/failure with model list

import { useEffect, useState, useRef } from "react";
import type { StepProps } from "../OnboardingWizard";
import { fetchWithAuth } from "@/services/apiClient";
import { Button } from "@/components/ui/button";
import { Loader2, CheckCircle2, XCircle, RefreshCw } from "lucide-react";

interface ValidationResult {
  valid: boolean;
  model_list?: string[];
  error?: string;
}

type ValidationState = "idle" | "loading" | "success" | "error";

const ValidateStep = ({ data, onUpdate }: StepProps) => {
  const [validationState, setValidationState] = useState<ValidationState>("idle");
  const [errorMessage, setErrorMessage] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const hasAutoValidated = useRef(false);

  const validate = async () => {
    setValidationState("loading");
    setErrorMessage("");
    setModels([]);

    try {
      const result = await fetchWithAuth<ValidationResult>("/setup/validate-key", {
        method: "POST",
        requiresAuth: false,
        body: JSON.stringify({
          provider: data.provider,
          api_key: data.apiKey,
          endpoint: data.endpoint || undefined,
        }),
      });

      if (result.valid) {
        setValidationState("success");
        const modelList = result.model_list ?? [];
        setModels(modelList);
        onUpdate({ validatedModels: modelList, validationAttempted: true });
      } else {
        setValidationState("error");
        setErrorMessage(result.error ?? "Validation failed");
        onUpdate({ validatedModels: [], validationAttempted: true });
      }
    } catch (err) {
      setValidationState("error");
      setErrorMessage(err instanceof Error ? err.message : "Connection failed");
      onUpdate({ validatedModels: [], validationAttempted: true });
    }
  };

  // Auto-validate on mount
  useEffect(() => {
    if (!hasAutoValidated.current && (data.apiKey || data.endpoint)) {
      hasAutoValidated.current = true;
      validate();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Validate connection</h2>
        <p className="text-sm text-muted-foreground">
          Testing your {data.provider} configuration...
        </p>
      </div>

      <div className="flex flex-col items-center gap-4 py-4">
        {validationState === "loading" && (
          <div className="flex flex-col items-center gap-2">
            <Loader2 className="h-10 w-10 animate-spin text-primary" />
            <p className="text-sm text-muted-foreground">Validating API key...</p>
          </div>
        )}

        {validationState === "success" && (
          <div className="flex flex-col items-center gap-2">
            <CheckCircle2 className="h-10 w-10 text-green-500" />
            <p className="text-sm font-medium text-green-600 dark:text-green-400">
              Connection successful
            </p>
            {models.length > 0 && (
              <div className="mt-2 w-full max-h-32 overflow-y-auto rounded-md border border-border p-2">
                <p className="mb-1 text-xs font-medium text-muted-foreground">
                  Available models ({models.length}):
                </p>
                <ul className="space-y-0.5">
                  {models.slice(0, 10).map((model) => (
                    <li key={model} className="text-xs text-foreground truncate">
                      {model}
                    </li>
                  ))}
                  {models.length > 10 && (
                    <li className="text-xs text-muted-foreground">
                      ...and {models.length - 10} more
                    </li>
                  )}
                </ul>
              </div>
            )}
          </div>
        )}

        {validationState === "error" && (
          <div className="flex flex-col items-center gap-2">
            <XCircle className="h-10 w-10 text-destructive" />
            <p className="text-sm font-medium text-destructive">Connection failed</p>
            <p className="text-xs text-muted-foreground text-center max-w-sm">
              {errorMessage}
            </p>
            <div className="flex gap-2 mt-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  hasAutoValidated.current = false;
                  validate();
                }}
                className="gap-1"
              >
                <RefreshCw className="h-3 w-3" />
                Try again
              </Button>
            </div>
            <p className="text-xs text-muted-foreground mt-2">
              You can continue and configure your provider later in Settings.
            </p>
          </div>
        )}

        {validationState === "idle" && (
          <Button onClick={validate} className="gap-1">
            Test Connection
          </Button>
        )}
      </div>
    </div>
  );
};

export default ValidateStep;
