// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { cn } from "@/lib/utils";
import { useDelayedShow } from "@/hooks/useDelayedShow";

function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  const show = useDelayedShow(300);
  if (!show) return null;

  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-md border border-border/30 bg-card/40 backdrop-blur-sm",
        className
      )}
      {...props}
    >
      <div className="absolute inset-0 -translate-x-full animate-shimmer bg-gradient-to-r from-transparent via-foreground/[0.03] to-transparent" />
    </div>
  );
}


export { Skeleton };
