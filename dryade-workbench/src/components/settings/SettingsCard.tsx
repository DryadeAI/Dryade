// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { cn } from "@/lib/utils";

interface SettingsCardProps {
  title?: string;
  description?: string;
  children: React.ReactNode;
  className?: string;
}

export const SettingsCard = ({ title, description, children, className }: SettingsCardProps) => (
  <div className={cn("rounded-lg border border-border bg-card shadow-sm", className)}>
    {(title || description) && (
      <div className="px-5 py-4 border-b border-border">
        {title && <h3 className="text-sm font-semibold text-foreground">{title}</h3>}
        {description && <p className="text-xs text-muted-foreground mt-0.5">{description}</p>}
      </div>
    )}
    <div className="px-5 py-3 space-y-0">{children}</div>
  </div>
);

export const SettingRow = ({
  label,
  description,
  children,
  className,
}: {
  label: string;
  description?: string;
  children: React.ReactNode;
  className?: string;
}) => (
  <div className={cn("flex items-center justify-between py-3 min-h-[44px]", className)}>
    <div className="space-y-0.5 flex-1 mr-4">
      <p className="text-sm font-medium text-foreground">{label}</p>
      {description && <p className="text-xs text-muted-foreground">{description}</p>}
    </div>
    <div className="shrink-0">{children}</div>
  </div>
);
