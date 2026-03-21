// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// FailoverToast — shows a sonner toast when the backend switches LLM providers.
// Called from the chat streaming handler when a "failover" SSE event is received.

import { toast } from "sonner";
import { fetchWithAuth } from "@/services/apiClient";

/**
 * Cancel an in-flight fallback for a session.
 * Calls POST /api/chat/{sessionId}/cancel-fallback.
 */
async function cancelFallback(sessionId: string): Promise<void> {
  try {
    await fetchWithAuth(`/api/chat/${sessionId}/cancel-fallback`, {
      method: "POST",
      requiresAuth: true,
    });
    toast.info("Fallback cancelled");
  } catch {
    // Silently ignore — the session may have already completed
  }
}

/**
 * Show a failover notification toast.
 *
 * Displayed when the backend switches from one LLM provider to another
 * during streaming. The "Stop" action button cancels the in-flight
 * fallback request.
 *
 * @param fromProvider  The provider that became unavailable (e.g. "openai")
 * @param toProvider    The provider being tried next (e.g. "anthropic")
 * @param sessionId     The conversation/session ID for the cancel endpoint
 */
export function showFailoverToast(
  fromProvider: string,
  toProvider: string,
  sessionId: string
): void {
  toast(`Switching to ${toProvider}\u2026`, {
    description: `${fromProvider} is unavailable`,
    duration: 5000,
    action: {
      label: "Stop",
      onClick: () => void cancelFallback(sessionId),
    },
  });
}
