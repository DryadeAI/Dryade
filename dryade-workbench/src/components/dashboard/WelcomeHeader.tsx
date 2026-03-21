// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { cn } from "@/lib/utils";
import { CheckCircle2, AlertCircle, XCircle } from "lucide-react";

type SystemStatus = 'healthy' | 'degraded' | 'unhealthy';

interface WelcomeHeaderProps {
  userName?: string;
  systemStatus: SystemStatus;
  statusMessage?: string;
}

const statusConfig = {
  healthy: {
    icon: CheckCircle2,
    label: "All systems operational",
    color: "text-success",
    bg: "bg-success/10",
    border: "border-success/20",
  },
  degraded: {
    icon: AlertCircle,
    label: "Some services degraded",
    color: "text-warning",
    bg: "bg-warning/10",
    border: "border-warning/20",
  },
  unhealthy: {
    icon: XCircle,
    label: "Service issues detected",
    color: "text-destructive",
    bg: "bg-destructive/10",
    border: "border-destructive/20",
  },
};

const WelcomeHeader = ({ userName, systemStatus, statusMessage }: WelcomeHeaderProps) => {
  const config = statusConfig[systemStatus];
  const StatusIcon = config.icon;

  return (
    <header className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold text-foreground glow-text-sm">
          {userName ? `Welcome back, ${userName}` : "Welcome to Dryade"}
        </h1>
        <p className="text-muted-foreground text-sm">
          Here's what's happening with your AI workflows
        </p>
      </div>

      <div
        className={cn(
          "flex items-center gap-2 px-3 py-1.5 rounded-full text-sm",
          config.bg,
          config.border,
          "border"
        )}
        role="status"
        aria-label={`System status: ${config.label}`}
      >
        <StatusIcon size={14} className={config.color} />
        <span className={cn("font-medium", config.color)}>
          {statusMessage || config.label}
        </span>
      </div>
    </header>
  );
};

export default WelcomeHeader;
