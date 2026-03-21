// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-medium ring-offset-background transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:cursor-not-allowed [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground hover:bg-primary/80 hover:shadow-glow-sm active:bg-primary/70 disabled:bg-muted disabled:text-muted-foreground disabled:shadow-none",
        destructive:
          "bg-destructive text-destructive-foreground hover:bg-destructive/90 hover:shadow-[0_4px_6px_hsl(var(--destructive)/0.2)] active:bg-destructive/80",
        outline:
          "border border-primary bg-transparent text-primary hover:bg-primary/10 hover:shadow-glow-sm disabled:border-muted disabled:text-muted-foreground disabled:shadow-none",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        ghost:
          "bg-transparent text-foreground hover:bg-muted/40 active:bg-muted/60",
        link: "text-primary underline-offset-4 hover:underline",
        glass:
          "glass-card border-primary/20 hover:border-primary/40 hover:shadow-glow-sm",
        hero:
          "bg-gradient-to-r from-primary to-primary/80 text-primary-foreground font-semibold hover:opacity-90 shadow-glow-sm",
        success:
          "bg-success text-success-foreground hover:bg-success/90 shadow-glow-sm",
        warning:
          "bg-warning text-warning-foreground hover:bg-warning/90",
      },
      size: {
        default: "h-10 px-5 py-2.5",
        sm: "h-9 rounded-md px-3",
        lg: "h-11 rounded-lg px-8 text-base",
        xl: "h-12 rounded-lg px-10 text-base font-semibold",
        icon: "h-10 w-10",
        "icon-sm": "h-8 w-8",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  loading?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, loading, children, disabled, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        disabled={disabled || loading}
        {...props}
      >
        {asChild ? (
          children
        ) : (
          <>
            {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {children}
          </>
        )}
      </Comp>
    );
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };
