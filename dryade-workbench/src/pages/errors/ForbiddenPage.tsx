// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { Link, useSearchParams } from "react-router-dom";
import { ShieldX } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import ErrorLayout from "@/components/errors/ErrorLayout";

const ForbiddenPage = () => {
  const [searchParams] = useSearchParams();
  const resource = searchParams.get("resource");
  const requiredRole = searchParams.get("role");

  return (
    <ErrorLayout>
      <Card className="border-border/50">
        <CardContent className="pt-8 pb-8 space-y-6">
          <div className="w-16 h-16 mx-auto rounded-full bg-destructive/10 flex items-center justify-center">
            <ShieldX className="w-8 h-8 text-destructive" />
          </div>

          <div className="space-y-2">
            <h1 className="text-2xl font-semibold text-foreground">Access Denied</h1>
            <p className="text-muted-foreground">
              You don't have permission to access this resource.
            </p>
            <p className="text-sm text-muted-foreground">
              Contact your administrator if you believe this is an error.
            </p>
          </div>

          {(resource || requiredRole) && (
            <div className="bg-muted/50 rounded-lg p-4 text-left text-sm space-y-1">
              {resource && (
                <p className="text-muted-foreground">
                  <span className="font-medium">Resource:</span> {resource}
                </p>
              )}
              {requiredRole && (
                <p className="text-muted-foreground">
                  <span className="font-medium">Required role:</span> {requiredRole}
                </p>
              )}
            </div>
          )}

          <div className="flex flex-col gap-3">
            <Button asChild size="lg" className="w-full">
              <Link to="/workspace/dashboard">Go to Dashboard</Link>
            </Button>
            <Button variant="outline" size="lg" className="w-full" disabled>
              Request Access
            </Button>
          </div>
        </CardContent>
      </Card>
    </ErrorLayout>
  );
};

export default ForbiddenPage;
