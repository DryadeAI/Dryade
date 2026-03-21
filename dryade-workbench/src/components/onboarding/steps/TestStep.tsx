// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// TestStep -- test conversation (OPTIONAL step)
// Mini chat interface to verify the AI responds correctly

import { useState } from "react";
import type { StepProps } from "../OnboardingWizard";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { fetchWithAuth } from "@/services/apiClient";
import { Loader2, Send, PartyPopper } from "lucide-react";

const TestStep = ({ data, onUpdate }: StepProps) => {
  const [message, setMessage] = useState("Hello! Can you confirm you're working?");
  const [response, setResponse] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  const sendTest = async () => {
    if (!message.trim()) return;
    setIsLoading(true);
    setError("");
    setResponse("");

    try {
      // Use a simple non-streaming chat endpoint
      const result = await fetchWithAuth<{ response?: string; content?: string; message?: string }>(
        "/chat/quick",
        {
          method: "POST",
          body: JSON.stringify({ message: message.trim(), mode: "chat" }),
        }
      );
      const text = result.response ?? result.content ?? result.message ?? "Response received.";
      setResponse(text);
      onUpdate({ testCompleted: true });
    } catch (err) {
      // Even if the quick endpoint doesn't exist, mark as tested
      const errMsg = err instanceof Error ? err.message : "Could not reach chat endpoint";
      setError(errMsg);
      // Still allow proceeding -- the test step is optional
      onUpdate({ testCompleted: true });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Test your setup</h2>
        <p className="text-sm text-muted-foreground">
          Send a quick message to verify everything works.
        </p>
      </div>

      <div className="flex gap-2">
        <Input
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Type a test message..."
          onKeyDown={(e) => e.key === "Enter" && !isLoading && sendTest()}
          disabled={isLoading}
        />
        <Button onClick={sendTest} disabled={isLoading || !message.trim()} size="icon">
          {isLoading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
        </Button>
      </div>

      {response && (
        <div className="space-y-2">
          <div className="rounded-md border border-border bg-muted/30 p-3">
            <p className="text-sm whitespace-pre-wrap">{response}</p>
          </div>
          <div className="flex items-center justify-center gap-2 text-green-600 dark:text-green-400">
            <PartyPopper className="h-5 w-5" />
            <p className="text-sm font-medium">Everything is working. You're all set!</p>
          </div>
        </div>
      )}

      {error && (
        <div className="rounded-md border border-destructive/20 bg-destructive/5 p-3">
          <p className="text-xs text-destructive">{error}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Don't worry -- you can test the chat from the workspace.
          </p>
        </div>
      )}
    </div>
  );
};

export default TestStep;
