// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { Link, useLocation } from "react-router-dom";
import { ChevronRight, Home } from "lucide-react";
import { cn } from "@/lib/utils";

interface BreadcrumbItem {
  label: string;
  href?: string;
}

interface PageBreadcrumbProps {
  items: BreadcrumbItem[];
  className?: string;
}

const PageBreadcrumb = ({ items, className }: PageBreadcrumbProps) => {
  return (
    <nav
      aria-label="Breadcrumb"
      className={cn("flex items-center gap-1 text-sm", className)}
    >
      <Link
        to="/workspace/dashboard"
        className="text-muted-foreground hover:text-foreground transition-colors"
        aria-label="Home"
      >
        <Home size={14} />
      </Link>
      
      {items.map((item, idx) => (
        <span key={idx} className="flex items-center gap-1">
          <ChevronRight size={12} className="text-muted-foreground/50" />
          {item.href ? (
            <Link
              to={item.href}
              className="text-muted-foreground hover:text-foreground transition-colors"
            >
              {item.label}
            </Link>
          ) : (
            <span className="text-foreground font-medium">{item.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
};

export default PageBreadcrumb;
