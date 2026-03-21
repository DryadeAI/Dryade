// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useEffect, useRef, useCallback } from 'react';
import { clearTokens } from '../services/apiClient';

export type WebSocketState = 'connecting' | 'connected' | 'reconnecting' | 'disconnected' | 'error';

// ServerMessage envelope from backend (Phase 8)
interface ServerMessage {
  seq: number;
  type: string;
  data: unknown;
  timestamp: number;
}

interface UseWebSocketOptions {
  url: string;
  onMessage?: (data: unknown) => void;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (error: Event) => void;
  reconnect?: boolean;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
}

interface UseWebSocketReturn {
  state: WebSocketState;
  latencyMs: number | null;
  reconnectAttempt: number;
  send: (data: unknown) => void;
  disconnect: () => void;
  reconnect: () => void;
}

export const useWebSocket = (options: UseWebSocketOptions): UseWebSocketReturn => {
  const {
    url,
    onMessage,
    onOpen,
    onClose,
    onError,
    reconnect: shouldReconnect = true,
    reconnectInterval = 3000,
    maxReconnectAttempts = 5,
  } = options;

  const [state, setState] = useState<WebSocketState>('disconnected');
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  // BUG-04: Use ref instead of state to prevent reconnect loop.
  // State changes trigger re-renders which recreate the connect callback,
  // which triggers the useEffect, causing an infinite reconnect cycle.
  const reconnectAttemptRef = useRef(0);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const pingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const lastPingTime = useRef<number>(0);
  const lastSeqRef = useRef<number>(-1); // Track last received seq for session resume

  const cleanup = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (pingIntervalRef.current) {
      clearInterval(pingIntervalRef.current);
      pingIntervalRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  const connect = useCallback(() => {
    cleanup();
    setState('connecting');

    try {
      wsRef.current = new WebSocket(url);

      wsRef.current.onopen = () => {
        setState('connected');

        // Session resume (GAP-096): Send resume message if we have a last_seq
        if (lastSeqRef.current >= 0) {
          wsRef.current?.send(JSON.stringify({
            type: 'session_resume',
            last_seq: lastSeqRef.current
          }));
        }

        reconnectAttemptRef.current = 0;
        onOpen?.();

        // Remove client-initiated ping - server handles heartbeat (GAP-093)
        // We just respond to server heartbeat with pong
      };

      wsRef.current.onmessage = (event) => {
        try {
          const envelope = JSON.parse(event.data) as ServerMessage;

          // Track sequence number for session resume
          if (typeof envelope.seq === 'number') {
            lastSeqRef.current = envelope.seq;

            // Send acknowledgment (GAP-094)
            wsRef.current?.send(JSON.stringify({
              type: 'ack',
              seq: envelope.seq
            }));
          }

          // Handle protocol messages (don't pass to user callback)
          if (envelope.type === 'heartbeat') {
            // Respond to server heartbeat with pong (GAP-093)
            wsRef.current?.send(JSON.stringify({ type: 'pong' }));
            return;
          }

          if (envelope.type === 'pong') {
            // Handle pong for latency measurement
            setLatencyMs(Date.now() - lastPingTime.current);
            return;
          }

          if (envelope.type === 'new_session') {
            // Protocol message, don't pass to user
            console.log('WebSocket session started:', envelope.data);
            return;
          }

          if (envelope.type === 'resumed') {
            // Protocol message, don't pass to user
            console.log('WebSocket session resumed:', envelope.data);
            return;
          }

          // Extract actual message data from envelope and pass to user callback
          onMessage?.(envelope.data);
        } catch {
          // Fallback for non-JSON or malformed messages
          onMessage?.(event.data);
        }
      };

      wsRef.current.onclose = (event) => {
        setState('disconnected');

        // Handle auth close codes (GAP-095)
        if (event.code === 4001) {
          // Unauthorized - clear tokens and force re-login
          console.log('WebSocket authentication failed, clearing tokens');
          clearTokens();
          window.location.href = '/auth';
          return;
        }

        if (event.code === 4003) {
          // Forbidden
          console.error('WebSocket connection forbidden');
          onError?.(new Event('Forbidden'));
          return;
        }

        onClose?.();

        // Exponential backoff (GAP-099)
        if (shouldReconnect && reconnectAttemptRef.current < maxReconnectAttempts) {
          setState('reconnecting');
          reconnectAttemptRef.current += 1;
          const backoffDelay = Math.min(
            reconnectInterval * Math.pow(2, reconnectAttemptRef.current - 1),
            30000 // Cap at 30 seconds
          );
          console.log(`Reconnecting in ${backoffDelay}ms (attempt ${reconnectAttemptRef.current})`);
          reconnectTimeoutRef.current = setTimeout(connect, backoffDelay);
        }
      };

      wsRef.current.onerror = (error) => {
        setState('error');
        onError?.(error);
      };
    } catch (error) {
      setState('error');
      console.error('WebSocket connection error:', error);
    }
  }, [url, onMessage, onOpen, onClose, onError, shouldReconnect, reconnectInterval, maxReconnectAttempts, cleanup]);

  const send = useCallback((data: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(typeof data === 'string' ? data : JSON.stringify(data));
    }
  }, []);

  const disconnect = useCallback(() => {
    cleanup();
    setState('disconnected');
    reconnectAttemptRef.current = 0;
  }, [cleanup]);

  const reconnectManually = useCallback(() => {
    reconnectAttemptRef.current = 0;
    connect();
  }, [connect]);

  useEffect(() => {
    connect();
    return cleanup;
  }, [connect, cleanup]);

  return {
    state,
    latencyMs,
    reconnectAttempt: reconnectAttemptRef.current,
    send,
    disconnect,
    reconnect: reconnectManually,
  };
};

export default useWebSocket;
