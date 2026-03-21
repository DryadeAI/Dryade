// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import * as React from "react";

import { cn } from "@/lib/utils";

const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<"input">>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
          className={cn(
            "flex h-[42px] w-full rounded-lg border border-border bg-card px-3 py-2 text-base text-foreground ring-offset-background transition-all duration-200",
            "file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground",
            "placeholder:text-muted-foreground",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 focus-visible:border-primary focus-visible:shadow-[0_0_0_2px_hsl(var(--primary)/0.4),0_0_12px_hsl(var(--primary)/0.15)]",
            "hover:border-muted-foreground/50",
            "disabled:cursor-not-allowed disabled:bg-muted/30 disabled:border-border disabled:text-muted-foreground",
            "md:text-sm",
            className
        )}
        ref={ref}
        {...props}
      />
    );
  }
);
Input.displayName = "Input";

export { Input };
