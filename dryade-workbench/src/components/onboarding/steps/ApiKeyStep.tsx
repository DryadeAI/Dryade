// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// ApiKeyStep -- API key entry (REQUIRED step)
// Masked input with show/hide toggle, provider-specific help text

import { useState } from "react";
import type { StepProps } from "../OnboardingWizard";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Eye, EyeOff } from "lucide-react";

const PROVIDER_HELP: Record<string, { url: string; label: string }> = {
  openai: { url: "https://platform.openai.com/api-keys", label: "Get your OpenAI key at platform.openai.com" },
  anthropic: { url: "https://console.anthropic.com/settings/keys", label: "Get your Anthropic key at console.anthropic.com" },
  google: { url: "https://aistudio.google.com/app/apikey", label: "Get your Google AI key at aistudio.google.com" },
  mistral: { url: "https://console.mistral.ai/api-keys", label: "Get your Mistral key at console.mistral.ai" },
  groq: { url: "https://console.groq.com/keys", label: "Get your Groq key at console.groq.com" },
};

const ApiKeyStep = ({ data, onUpdate }: StepProps) => {
  const [showKey, setShowKey] = useState(false);
  const isLocal = data.provider === "vllm" || data.provider === "other";
  const help = PROVIDER_HELP[data.provider];

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">
          {isLocal ? "Configure connection" : "Enter your API key"}
        </h2>
        <p className="text-sm text-muted-foreground">
          {isLocal
            ? "Provide the API key for your local server (leave empty if not required)."
            : "Your key is stored locally and never leaves your machine."}
        </p>
      </div>

      {!isLocal && (
        <div className="space-y-2">
          <Label htmlFor="api-key">API Key</Label>
          <div className="relative">
            <Input
              id="api-key"
              type={showKey ? "text" : "password"}
              placeholder={`sk-...`}
              value={data.apiKey}
              onChange={(e) => onUpdate({ apiKey: e.target.value })}
              autoComplete="off"
              data-1p-ignore
              data-lpignore="true"
              className="pr-10"
            />
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="absolute right-1 top-1/2 -translate-y-1/2 h-7 w-7 p-0"
              onClick={() => setShowKey(!showKey)}
            >
              {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </Button>
          </div>
          {help && (
            <p className="text-xs text-muted-foreground">
              <a
                href={help.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary hover:underline"
              >
                {help.label}
              </a>
            </p>
          )}
        </div>
      )}

      {isLocal && (
        <>
          <div className="space-y-2">
            <Label htmlFor="local-endpoint">Endpoint URL</Label>
            <Input
              id="local-endpoint"
              placeholder="http://localhost:8000/v1"
              value={data.endpoint}
              onChange={(e) => onUpdate({ endpoint: e.target.value })}
              autoComplete="off"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="local-key">API Key (optional)</Label>
            <div className="relative">
              <Input
                id="local-key"
                type={showKey ? "text" : "password"}
                placeholder="Leave empty if not required"
                value={data.apiKey}
                onChange={(e) => onUpdate({ apiKey: e.target.value })}
                autoComplete="off"
                data-1p-ignore
                data-lpignore="true"
                className="pr-10"
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="absolute right-1 top-1/2 -translate-y-1/2 h-7 w-7 p-0"
                onClick={() => setShowKey(!showKey)}
              >
                {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default ApiKeyStep;
