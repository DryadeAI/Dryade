// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { Link, useSearchParams } from "react-router-dom";
import { Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import ErrorLayout from "@/components/errors/ErrorLayout";

const UnauthorizedPage = () => {
  const [searchParams] = useSearchParams();
  const redirect = searchParams.get("redirect") || "/workspace/dashboard";

  return (
    <ErrorLayout>
      <Card className="border-border/50">
        <CardContent className="pt-8 pb-8 space-y-6">
          <div className="w-16 h-16 mx-auto rounded-full bg-warning/10 flex items-center justify-center">
            <Lock className="w-8 h-8 text-warning" />
          </div>

          <div className="space-y-2">
            <h1 className="text-2xl font-semibold text-foreground">Please Log In</h1>
            <p className="text-muted-foreground">
              You need to be logged in to access this page.
            </p>
            <p className="text-sm text-muted-foreground">
              Your session may have expired.
            </p>
          </div>

          <div className="flex flex-col gap-3">
            <Button asChild size="lg" className="w-full">
              <Link to={`/auth?redirect=${encodeURIComponent(redirect)}`}>
                Log In
              </Link>
            </Button>
            <Button asChild variant="ghost" size="lg" className="w-full">
              <Link to="/">Return to Home</Link>
            </Button>
          </div>
        </CardContent>
      </Card>
    </ErrorLayout>
  );
};

export default UnauthorizedPage;
