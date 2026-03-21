// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// PreferencesStep -- workspace preferences (OPTIONAL step)
// Theme selection and default model from validated models

import type { StepProps } from "../OnboardingWizard";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { Monitor, Sun, Moon } from "lucide-react";

const PreferencesStep = ({ data, onUpdate }: StepProps) => {
  const theme = (data.preferences?.theme as string) ?? "system";
  const defaultModel = (data.preferences?.default_model as string) ?? "";

  const setPreference = (key: string, value: string) => {
    onUpdate({
      preferences: { ...data.preferences, [key]: value },
    });
  };

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-semibold">Preferences</h2>
        <p className="text-sm text-muted-foreground">
          Customize your workspace. You can change these anytime in Settings.
        </p>
      </div>

      {/* Theme selection */}
      <div className="space-y-2">
        <Label className="text-sm font-medium">Theme</Label>
        <RadioGroup
          value={theme}
          onValueChange={(v) => setPreference("theme", v)}
          className="flex gap-3"
        >
          {[
            { value: "system", label: "System", icon: Monitor },
            { value: "light", label: "Light", icon: Sun },
            { value: "dark", label: "Dark", icon: Moon },
          ].map((opt) => {
            const Icon = opt.icon;
            return (
              <Label
                key={opt.value}
                htmlFor={`theme-${opt.value}`}
                className={`flex cursor-pointer flex-col items-center gap-1 rounded-lg border p-3 transition-colors hover:bg-muted/50 ${
                  theme === opt.value
                    ? "border-primary bg-primary/5"
                    : "border-border"
                }`}
              >
                <RadioGroupItem
                  value={opt.value}
                  id={`theme-${opt.value}`}
                  className="sr-only"
                />
                <Icon className="h-5 w-5 text-muted-foreground" />
                <span className="text-xs font-medium">{opt.label}</span>
              </Label>
            );
          })}
        </RadioGroup>
      </div>

      {/* Default model selection */}
      {data.validatedModels.length > 0 && (
        <div className="space-y-2">
          <Label htmlFor="default-model" className="text-sm font-medium">
            Default model
          </Label>
          <select
            id="default-model"
            value={defaultModel}
            onChange={(e) => setPreference("default_model", e.target.value)}
            className="flex h-[42px] w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50"
          >
            <option value="">Select a model...</option>
            {data.validatedModels.slice(0, 20).map((model) => (
              <option key={model} value={model}>
                {model}
              </option>
            ))}
          </select>
        </div>
      )}
    </div>
  );
};

export default PreferencesStep;
