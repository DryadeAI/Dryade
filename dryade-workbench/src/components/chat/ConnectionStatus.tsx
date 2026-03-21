// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import React from "react";
import { cn } from "@/lib/utils";
import { Wifi, WifiOff, RefreshCw, Loader2, AlertCircle, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

// Extended to match COMPONENTS-4.md spec
type ConnectionState = "connected" | "connecting" | "reconnecting" | "disconnected" | "error";

interface ConnectionStatusProps {
  status: ConnectionState;
  reconnectAttempt?: number;
  maxReconnects?: number;
  errorMessage?: string;
  latencyMs?: number;
  onReconnect?: () => void;
  className?: string;
}

const statusConfig: Record<
  ConnectionState,
  { icon: typeof Wifi; color: string; bgColor: string; label: string }
> = {
  connected: {
    icon: Check,
    color: "text-success",
    bgColor: "bg-success/10",
    label: "Connected",
  },
  connecting: {
    icon: Loader2,
    color: "text-warning",
    bgColor: "bg-warning/10",
    label: "Connecting...",
  },
  reconnecting: {
    icon: RefreshCw,
    color: "text-warning",
    bgColor: "bg-warning/10",
    label: "Reconnecting",
  },
  disconnected: {
    icon: WifiOff,
    color: "text-destructive",
    bgColor: "bg-destructive/10",
    label: "Disconnected",
  },
  error: {
    icon: AlertCircle,
    color: "text-destructive",
    bgColor: "bg-destructive/10",
    label: "Error",
  },
};

const ConnectionStatus = React.memo(function ConnectionStatus({
  status,
  reconnectAttempt,
  maxReconnects,
  errorMessage,
  latencyMs,
  onReconnect,
  className,
}: ConnectionStatusProps) {
  const state = status;
  const config = statusConfig[state];
  const StatusIcon = config.icon;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div
          tabIndex={0}
          role="status"
          aria-live="polite"
          aria-label={`Connection: ${config.label}`}
          className={cn(
            "flex items-center gap-2 px-2 py-1 rounded-full text-xs",
            config.bgColor,
            className
          )}
        >
          <StatusIcon
            size={12}
            className={cn(
              config.color,
              (state === "reconnecting" || state === "connecting") && "animate-spin"
            )}
          />
          <span className={config.color}>
            {state === "reconnecting" && reconnectAttempt && maxReconnects
              ? `Reconnecting (${reconnectAttempt}/${maxReconnects})`
              : state === "error" && errorMessage
              ? errorMessage
              : config.label}
          </span>
          {state === "connected" && latencyMs !== undefined && (
            <span className="text-muted-foreground font-mono">{latencyMs}ms</span>
          )}
          {(state === "disconnected" || state === "error") && onReconnect && (
            <Button
              variant="ghost"
              size="sm"
              className="h-8 px-1.5 text-xs"
              onClick={onReconnect}
            >
              Retry
            </Button>
          )}
        </div>
      </TooltipTrigger>
      <TooltipContent>
        <p>
          {state === "connected" && "WebSocket connection active"}
          {state === "connecting" && "Establishing connection..."}
          {state === "reconnecting" && "Attempting to reconnect..."}
          {state === "disconnected" && "Connection lost. Click retry to reconnect."}
          {state === "error" && (errorMessage || "Connection error occurred")}
        </p>
      </TooltipContent>
    </Tooltip>
  );
});

export default ConnectionStatus;
