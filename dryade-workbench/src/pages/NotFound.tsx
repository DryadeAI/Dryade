// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useLocation } from "react-router-dom";
import { useEffect } from "react";
import { TreePine } from "lucide-react";
import { Button } from "@/components/ui/button";

const NotFound = () => {
  const location = useLocation();

  useEffect(() => {
    console.error("404 Error: User attempted to access non-existent route:", location.pathname);
  }, [location.pathname]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="text-center space-y-6">
        <div className="relative inline-flex items-center justify-center">
          <div className="absolute w-32 h-32 rounded-full bg-primary/10 blur-2xl" />
          <TreePine className="relative w-16 h-16 text-muted-foreground" />
        </div>

        <h1 className="text-5xl font-bold text-foreground glow-text-lg">404</h1>
        <p className="text-lg text-muted-foreground">The forest has no path here.</p>
        <Button variant="outline" asChild>
          <a href="/">Return to the clearing</a>
        </Button>
      </div>
    </div>
  );
};

export default NotFound;
