// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// OnboardingWizard -- multi-step onboarding flow for first-time users
// Guides through: Provider -> API Key -> Validate -> MCP -> Preferences -> Test
// Required steps cannot be skipped; optional steps show "Set up later" with disclaimer

import { useReducer, useCallback } from "react";
import { useQueryClient, useMutation } from "@tanstack/react-query";
import { fetchWithAuth } from "@/services/apiClient";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "@/components/ui/tooltip";
import { ArrowLeft, ArrowRight, SkipForward, Sparkles } from "lucide-react";
import WizardProgress, { type WizardStep } from "./WizardProgress";
import ProviderStep from "./steps/ProviderStep";
import ApiKeyStep from "./steps/ApiKeyStep";
import ValidateStep from "./steps/ValidateStep";
import McpStep from "./steps/McpStep";
import PreferencesStep from "./steps/PreferencesStep";
import TestStep from "./steps/TestStep";

// ============================================================================
// Types
// ============================================================================

export interface WizardData {
  provider: string;
  apiKey: string;
  endpoint: string;
  validatedModels: string[];
  validationAttempted: boolean;
  mcpServers: Record<string, unknown>;
  preferences: Record<string, unknown>;
  testCompleted: boolean;
}

export interface StepProps {
  data: WizardData;
  onUpdate: (partial: Partial<WizardData>) => void;
  onNext: () => void;
  onBack: () => void;
  onSkip?: () => void;
}

// ============================================================================
// Step definitions
// ============================================================================

const STEPS: WizardStep[] = [
  { id: "provider", name: "Provider", required: true },
  { id: "api-key", name: "API Key", required: true },
  { id: "validate", name: "Validate", required: true },
  { id: "mcp", name: "MCP", required: false },
  { id: "preferences", name: "Preferences", required: false },
  { id: "test", name: "Test", required: false },
];

const SKIP_DISCLAIMERS: Record<string, string> = {
  mcp: "Without MCP servers, agents won't be able to use external tools (file access, web search, etc.)",
  preferences: "Default settings will be used. You can change them anytime in Settings.",
  test: "You can start chatting anytime from the workspace.",
};

// ============================================================================
// Reducer
// ============================================================================

interface WizardState {
  currentStep: number;
  data: WizardData;
  completedSteps: Set<string>;
  direction: "forward" | "backward";
}

type WizardAction =
  | { type: "NEXT" }
  | { type: "BACK" }
  | { type: "SKIP" }
  | { type: "UPDATE_DATA"; payload: Partial<WizardData> }
  | { type: "COMPLETE_STEP"; payload: string };

function wizardReducer(state: WizardState, action: WizardAction): WizardState {
  switch (action.type) {
    case "NEXT": {
      const currentStepId = STEPS[state.currentStep].id;
      const newCompleted = new Set(state.completedSteps);
      newCompleted.add(currentStepId);
      return {
        ...state,
        currentStep: Math.min(state.currentStep + 1, STEPS.length - 1),
        completedSteps: newCompleted,
        direction: "forward",
      };
    }
    case "BACK":
      return {
        ...state,
        currentStep: Math.max(state.currentStep - 1, 0),
        direction: "backward",
      };
    case "SKIP": {
      const currentStepId = STEPS[state.currentStep].id;
      const newCompleted = new Set(state.completedSteps);
      newCompleted.add(currentStepId);
      return {
        ...state,
        currentStep: Math.min(state.currentStep + 1, STEPS.length - 1),
        completedSteps: newCompleted,
        direction: "forward",
      };
    }
    case "UPDATE_DATA":
      return {
        ...state,
        data: { ...state.data, ...action.payload },
      };
    case "COMPLETE_STEP": {
      const newCompleted = new Set(state.completedSteps);
      newCompleted.add(action.payload);
      return { ...state, completedSteps: newCompleted };
    }
    default:
      return state;
  }
}

const initialState: WizardState = {
  currentStep: 0,
  data: {
    provider: "",
    apiKey: "",
    endpoint: "",
    validatedModels: [],
    validationAttempted: false,
    mcpServers: {},
    preferences: {},
    testCompleted: false,
  },
  completedSteps: new Set<string>(),
  direction: "forward",
};

// ============================================================================
// Component
// ============================================================================

interface OnboardingWizardProps {
  onComplete: () => void;
}

const OnboardingWizard = ({ onComplete }: OnboardingWizardProps) => {
  const [state, dispatch] = useReducer(wizardReducer, initialState);
  const queryClient = useQueryClient();

  const completeSetup = useMutation({
    mutationFn: () =>
      fetchWithAuth<{ status: string }>("/setup/complete", {
        method: "POST",
        requiresAuth: false,
        body: JSON.stringify({
          llm_provider: state.data.provider,
          llm_api_key: state.data.apiKey,
          llm_endpoint: state.data.endpoint || undefined,
          mcp_servers:
            Object.keys(state.data.mcpServers).length > 0
              ? state.data.mcpServers
              : undefined,
          preferences:
            Object.keys(state.data.preferences).length > 0
              ? state.data.preferences
              : undefined,
        }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["setup-status"] });
      onComplete();
    },
  });

  const handleNext = useCallback(() => {
    // If on the last step, complete setup
    if (state.currentStep === STEPS.length - 1) {
      completeSetup.mutate();
      return;
    }
    dispatch({ type: "NEXT" });
  }, [state.currentStep, completeSetup]);

  const handleBack = useCallback(() => {
    dispatch({ type: "BACK" });
  }, []);

  const handleSkip = useCallback(() => {
    if (state.currentStep === STEPS.length - 1) {
      completeSetup.mutate();
      return;
    }
    dispatch({ type: "SKIP" });
  }, [state.currentStep, completeSetup]);

  const handleUpdate = useCallback((partial: Partial<WizardData>) => {
    dispatch({ type: "UPDATE_DATA", payload: partial });
  }, []);

  const currentStepDef = STEPS[state.currentStep];
  const isOptional = !currentStepDef.required;
  const isLastStep = state.currentStep === STEPS.length - 1;
  const disclaimer = SKIP_DISCLAIMERS[currentStepDef.id];

  // Step-specific "can proceed" checks
  const canProceed = (() => {
    switch (currentStepDef.id) {
      case "provider":
        return !!state.data.provider;
      case "api-key": {
        const isLocal = state.data.provider === "vllm" || state.data.provider === "other";
        return !!(state.data.apiKey || (isLocal && state.data.endpoint));
      }
      case "validate":
        // Allow proceeding even if validation failed — user may fix provider later
        return state.data.validatedModels.length > 0 || state.data.validationAttempted === true;
      default:
        return true; // Optional steps always allow proceed
    }
  })();

  // Render current step
  const stepProps: StepProps = {
    data: state.data,
    onUpdate: handleUpdate,
    onNext: handleNext,
    onBack: handleBack,
    onSkip: isOptional ? handleSkip : undefined,
  };

  const StepComponent = (() => {
    switch (currentStepDef.id) {
      case "provider":
        return <ProviderStep {...stepProps} />;
      case "api-key":
        return <ApiKeyStep {...stepProps} />;
      case "validate":
        return <ValidateStep {...stepProps} />;
      case "mcp":
        return <McpStep {...stepProps} />;
      case "preferences":
        return <PreferencesStep {...stepProps} />;
      case "test":
        return <TestStep {...stepProps} />;
      default:
        return null;
    }
  })();

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background p-4">
      {/* Header */}
      <div className="mb-8 text-center">
        <div className="mb-3 flex items-center justify-center gap-2">
          <Sparkles className="h-6 w-6 text-primary" />
          <h1 className="text-2xl font-bold tracking-tight">Welcome to Dryade</h1>
        </div>
        <p className="text-sm text-muted-foreground">
          Let's get your AI workspace configured in a few steps.
        </p>
      </div>

      {/* Progress indicator */}
      <div className="mb-6 w-full max-w-2xl">
        <WizardProgress
          steps={STEPS}
          currentIndex={state.currentStep}
          completedSteps={state.completedSteps}
        />
      </div>

      {/* Step content */}
      <Card className="w-full max-w-lg">
        <CardContent className="p-6">
          <div
            className="transition-opacity duration-200 ease-in-out"
            key={currentStepDef.id}
          >
            {StepComponent}
          </div>
        </CardContent>
      </Card>

      {/* Navigation footer */}
      <div className="mt-6 flex w-full max-w-lg items-center justify-between">
        <Button
          variant="ghost"
          size="sm"
          onClick={handleBack}
          disabled={state.currentStep === 0}
          className="gap-1"
        >
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>

        <div className="flex items-center gap-2">
          {isOptional && disclaimer && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleSkip}
                  className="gap-1 text-muted-foreground"
                >
                  <SkipForward className="h-4 w-4" />
                  Set up later
                </Button>
              </TooltipTrigger>
              <TooltipContent className="max-w-[250px] text-center">
                <p className="text-xs">{disclaimer}</p>
              </TooltipContent>
            </Tooltip>
          )}

          <Button
            size="sm"
            onClick={handleNext}
            disabled={!canProceed || completeSetup.isPending}
            className="gap-1"
          >
            {completeSetup.isPending ? (
              "Saving..."
            ) : isLastStep ? (
              "Finish Setup"
            ) : (
              <>
                Next
                <ArrowRight className="h-4 w-4" />
              </>
            )}
          </Button>
        </div>
      </div>

      {completeSetup.isError && (
        <p className="mt-3 text-sm text-destructive">
          Failed to save configuration. Please try again.
        </p>
      )}
    </div>
  );
};

export default OnboardingWizard;
