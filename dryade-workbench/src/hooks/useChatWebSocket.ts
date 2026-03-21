// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// Chat WebSocket Hook - Real-time chat with sequencing and acknowledgments
// Based on COMPONENTS-API-4.md WebSocket specification

import { useState, useEffect, useRef, useCallback } from "react";
import { clearTokens } from "@/services/apiClient";

export type ChatWSStatus = "connected" | "connecting" | "reconnecting" | "disconnected" | "error";

/** Generic WS event forwarded to the consumer via onEvent */
export interface WSEvent {
  seq: number;
  type: string;
  data: Record<string, unknown>;
}

export interface SendMessageOptions {
  mode?: string;
  enable_thinking?: boolean;
  crew_id?: string;
  leash_preset?: string;
  event_visibility?: string;
  image_attachments?: Array<{ base64: string; mime_type: string }>;
}

interface UseChatWebSocketOptions {
  conversationId: string;
  token?: string;
  onEvent?: (event: WSEvent) => void;
  onComplete?: () => void;
  onError?: (error: string) => void;
  onClarification?: (prompt: string, options: string[]) => void;
  enabled?: boolean;
}

interface UseChatWebSocketReturn {
  status: ChatWSStatus;
  latencyMs: number | null;
  reconnectAttempt: number;
  maxReconnects: number;
  sendMessage: (content: string, options?: SendMessageOptions) => void;
  cancelStream: () => void;
  reconnect: () => void;
  disconnect: () => void;
}

const MAX_RECONNECT_ATTEMPTS = 5;
const RECONNECT_INTERVAL = 3000;

export const useChatWebSocket = (options: UseChatWebSocketOptions): UseChatWebSocketReturn => {
  const {
    conversationId,
    token,
    onEvent,
    onComplete,
    onError,
    onClarification,
    enabled = true,
  } = options;

  const [status, setStatus] = useState<ChatWSStatus>("disconnected");
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const [reconnectAttempt, setReconnectAttempt] = useState(0);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectCountRef = useRef(0);
  const lastSequenceRef = useRef<number>(0);
  const sessionIdRef = useRef<string | null>(null);
  const pendingMessagesRef = useRef<string[]>([]);
  const awaitingAuthRef = useRef(false);

  // Store callbacks in refs so connect() doesn't depend on them
  const onEventRef = useRef(onEvent);
  const onCompleteRef = useRef(onComplete);
  const onErrorRef = useRef(onError);
  const onClarificationRef = useRef(onClarification);
  onEventRef.current = onEvent;
  onCompleteRef.current = onComplete;
  onErrorRef.current = onError;
  onClarificationRef.current = onClarification;

  const cleanup = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.onclose = null; // prevent reconnect on intentional close
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  const connect = useCallback(() => {
    if (!enabled || !conversationId) return;

    cleanup();
    setStatus("connecting");

    try {
      // Build WebSocket URL WITHOUT token (SEC-02: no JWT in URL)
      const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const baseUrl = `${wsProtocol}//${window.location.host}`;
      const wsUrl = `${baseUrl}/ws/chat/${conversationId}`;

      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        // Authenticate via first message instead of URL query param (SEC-02)
        if (token) {
          ws.send(JSON.stringify({ type: "auth", token }));
          // Defer pending message flush until auth is confirmed (new_session event)
          // to avoid race where server drops messages arriving before auth completes
          awaitingAuthRef.current = true;
        } else {
          awaitingAuthRef.current = false;
        }

        const wasReconnect = reconnectCountRef.current > 0;
        setStatus("connected");
        reconnectCountRef.current = 0;
        setReconnectAttempt(0);

        // Notify hooks that WS is (re)connected so they can refresh stale state
        if (wasReconnect) {
          window.dispatchEvent(new CustomEvent("dryade:ws_reconnected"));
        }

        // Send session resume if we have prior sequence state
        if (sessionIdRef.current && lastSequenceRef.current > 0) {
          ws.send(
            JSON.stringify({
              type: "resume",
              last_seq: lastSequenceRef.current,
            })
          );
        }

        // Flush pending messages only if no auth handshake to wait for
        if (!awaitingAuthRef.current) {
          const pending = pendingMessagesRef.current;
          if (pending.length > 0) {
            pendingMessagesRef.current = [];
            for (const msg of pending) {
              ws.send(msg);
            }
          }
        }
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          handleMessage(data);
        } catch (err) {
          console.error("Failed to parse WS message:", err);
        }
      };

      ws.onclose = (event) => {
        wsRef.current = null;

        // Handle auth error codes
        if (event.code === 4001) {
          setStatus("error");
          onErrorRef.current?.("Authentication required");
          clearTokens();
          return;
        }
        if (event.code === 4003) {
          setStatus("error");
          onErrorRef.current?.("Access forbidden");
          return;
        }

        // Auto-reconnect with exponential backoff
        const attempt = reconnectCountRef.current;
        if (attempt < MAX_RECONNECT_ATTEMPTS) {
          setStatus("reconnecting");
          reconnectCountRef.current = attempt + 1;
          setReconnectAttempt(attempt + 1);
          const backoffMs = Math.min(
            RECONNECT_INTERVAL * Math.pow(2, attempt),
            30000
          );
          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, backoffMs);
        } else {
          setStatus("disconnected");
        }
      };

      ws.onerror = () => {
        // onerror is always followed by onclose, so just log
        console.warn("WebSocket connection error for", conversationId);
      };
    } catch (error) {
      console.error("Failed to create WebSocket:", error);
      setStatus("error");
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId, token, enabled, cleanup]);

  // Message handler as a stable function (uses refs for callbacks)
  function handleMessage(data: Record<string, unknown>) {
    const seq = typeof data.seq === "number" ? (data.seq as number) : undefined;
    if (seq !== undefined) {
      lastSequenceRef.current = seq;
      // Send ack
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: "ack", seq }));
      }
    }

    const msgType = data.type as string;

    // Protocol messages handled internally
    if (msgType === "new_session" || msgType === "session") {
      sessionIdRef.current = (data.data as Record<string, unknown>)?.session_id as string
        || data.session_id as string
        || conversationId;

      // Auth confirmed — flush any messages queued during the auth handshake
      if (awaitingAuthRef.current) {
        awaitingAuthRef.current = false;
        const pending = pendingMessagesRef.current;
        if (pending.length > 0 && wsRef.current?.readyState === WebSocket.OPEN) {
          pendingMessagesRef.current = [];
          for (const msg of pending) {
            wsRef.current.send(msg);
          }
        }
      }
      return;
    }
    if (msgType === "resumed") return;

    // Heartbeat - respond with pong
    if (msgType === "heartbeat") {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: "pong" }));
      }
      const serverTime = (data.data as Record<string, unknown>)?.server_time as number
        || data.timestamp as number;
      if (serverTime) {
        setLatencyMs(Math.round((Date.now() / 1000 - serverTime) * 1000));
      }
      return;
    }

    // Message ack - internal protocol
    if (msgType === "message_ack") return;

    // Rate limiting
    if (msgType === "error" && (data.code === "RATE_LIMITED" || data.code === "rate_limited")) {
      const retryAfter = (data.retry_after as number) || 5;
      onErrorRef.current?.(`Rate limited. Retry after ${retryAfter} seconds.`);
      return;
    }

    // Forward ALL application-level messages to onEvent
    const eventData = (data.data as Record<string, unknown>) || {};
    if (seq !== undefined && onEventRef.current) {
      onEventRef.current({ seq, type: msgType, data: eventData });
    }

    // System-wide events dispatched on window for cross-hook consumption
    if (msgType === "plugins_changed") {
      window.dispatchEvent(new CustomEvent("dryade:plugins_changed", { detail: eventData }));
      return;
    }

    // Backward-compat specific callbacks
    if (msgType === "complete") {
      onCompleteRef.current?.();
    } else if (msgType === "error") {
      onErrorRef.current?.((eventData.message as string) || (data.message as string) || "Unknown error");
    } else if (msgType === "clarification" || msgType === "clarify") {
      onClarificationRef.current?.(
        (eventData.prompt as string) || (data.prompt as string) || "",
        (eventData.options as string[]) || (data.options as string[]) || []
      );
    }
  }

  const sendMessage = useCallback((content: string, options?: SendMessageOptions) => {
    const message: Record<string, unknown> = {
      type: "message",
      content,
      timestamp: new Date().toISOString(),
    };
    if (options?.mode) message.mode = options.mode;
    if (options?.enable_thinking) message.enable_thinking = options.enable_thinking;
    if (options?.crew_id) message.crew_id = options.crew_id;
    if (options?.leash_preset) message.leash_preset = options.leash_preset;
    if (options?.event_visibility) message.event_visibility = options.event_visibility;
    if (options?.image_attachments?.length) message.image_attachments = options.image_attachments;

    const payload = JSON.stringify(message);
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(payload);
    } else {
      // Queue for delivery when connection opens (handles new-conversation race)
      pendingMessagesRef.current.push(payload);
    }
  }, []);

  const cancelStream = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "cancel" }));
    }
  }, []);

  const disconnect = useCallback(() => {
    cleanup();
    pendingMessagesRef.current = [];
    reconnectCountRef.current = 0;
    setReconnectAttempt(0);
    setStatus("disconnected");
  }, [cleanup]);

  const reconnectManually = useCallback(() => {
    reconnectCountRef.current = 0;
    setReconnectAttempt(0);
    connect();
  }, [connect]);

  // Connect/disconnect based on enabled + conversationId
  useEffect(() => {
    if (enabled && conversationId) {
      connect();
    } else {
      cleanup();
      setStatus("disconnected");
    }
    return () => {
      cleanup();
    };
  }, [enabled, conversationId, connect, cleanup]);

  return {
    status,
    latencyMs,
    reconnectAttempt,
    maxReconnects: MAX_RECONNECT_ATTEMPTS,
    sendMessage,
    cancelStream,
    reconnect: reconnectManually,
    disconnect,
  };
};

export default useChatWebSocket;
