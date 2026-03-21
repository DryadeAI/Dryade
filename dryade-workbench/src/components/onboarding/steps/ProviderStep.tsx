// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// ProviderStep -- LLM provider selection (REQUIRED step)
// User selects their LLM provider from a list of supported options

import type { StepProps } from "../OnboardingWizard";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import {
  Bot,
  Cloud,
  Server,
  Cpu,
  Zap,
  Sparkles,
  MoreHorizontal,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

interface ProviderOption {
  value: string;
  label: string;
  description: string;
  icon: LucideIcon;
}

const PROVIDERS: ProviderOption[] = [
  { value: "openai", label: "OpenAI", description: "GPT-4o, o3, o4-mini", icon: Sparkles },
  { value: "anthropic", label: "Anthropic", description: "Claude Opus, Sonnet, Haiku", icon: Bot },
  { value: "vllm", label: "Local / vLLM", description: "Self-hosted models via vLLM or compatible API", icon: Server },
  { value: "google", label: "Google", description: "Gemini Pro, Flash", icon: Cloud },
  { value: "mistral", label: "Mistral", description: "Mistral Large, Medium, Small", icon: Zap },
  { value: "groq", label: "Groq", description: "Fast inference for open models", icon: Cpu },
  { value: "other", label: "Other", description: "Any OpenAI-compatible endpoint", icon: MoreHorizontal },
];

const ProviderStep = ({ data, onUpdate }: StepProps) => {
  const showEndpoint = data.provider === "vllm" || data.provider === "other";

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Choose your LLM provider</h2>
        <p className="text-sm text-muted-foreground">
          Select the AI provider you want to use with Dryade.
        </p>
      </div>

      <RadioGroup
        value={data.provider}
        onValueChange={(value) => onUpdate({ provider: value })}
        className="grid gap-2"
      >
        {PROVIDERS.map((p) => {
          const Icon = p.icon;
          return (
            <Label
              key={p.value}
              htmlFor={`provider-${p.value}`}
              className={`flex cursor-pointer items-center gap-3 rounded-lg border p-3 transition-colors hover:bg-muted/50 ${
                data.provider === p.value
                  ? "border-primary bg-primary/5"
                  : "border-border"
              }`}
            >
              <RadioGroupItem value={p.value} id={`provider-${p.value}`} />
              <Icon className="h-5 w-5 text-muted-foreground" />
              <div className="flex-1">
                <span className="text-sm font-medium">{p.label}</span>
                <p className="text-xs text-muted-foreground">{p.description}</p>
              </div>
            </Label>
          );
        })}
      </RadioGroup>

      {showEndpoint && (
        <div className="space-y-2 pt-2">
          <Label htmlFor="endpoint">Endpoint URL</Label>
          <Input
            id="endpoint"
            placeholder="http://localhost:8000/v1"
            value={data.endpoint}
            onChange={(e) => onUpdate({ endpoint: e.target.value })}
          />
          <p className="text-xs text-muted-foreground">
            The base URL of your OpenAI-compatible API server.
          </p>
        </div>
      )}
    </div>
  );
};

export default ProviderStep;
