// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import * as React from "react";

import { cn } from "@/lib/utils";

export type TextareaProps = React.TextareaHTMLAttributes<HTMLTextAreaElement>;

const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(({ className, ...props }, ref) => {
  return (
    <textarea
      className={cn(
        "flex min-h-[80px] w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground ring-offset-background placeholder:text-muted-foreground hover:border-muted-foreground/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 focus-visible:border-primary focus-visible:shadow-[0_0_0_2px_hsl(var(--primary)/0.4),0_0_12px_hsl(var(--primary)/0.15)] disabled:cursor-not-allowed disabled:bg-muted/30 disabled:border-border disabled:text-muted-foreground",
        className,
      )}
      ref={ref}
      {...props}
    />
  );
});
Textarea.displayName = "Textarea";

export { Textarea };
