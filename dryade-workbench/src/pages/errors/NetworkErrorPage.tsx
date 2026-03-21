// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { WifiOff, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import ErrorLayout from "@/components/errors/ErrorLayout";
import { toast } from "sonner";

const NetworkErrorPage = () => {
  const navigate = useNavigate();
  const [isRetrying, setIsRetrying] = useState(false);

  useEffect(() => {
    const handleOnline = () => {
      toast.success("Connection Restored!", { description: "You're back online." });
      navigate(-1);
    };

    window.addEventListener("online", handleOnline);
    return () => window.removeEventListener("online", handleOnline);
  }, [navigate]);

  const handleRetry = () => {
    setIsRetrying(true);

    // Check if we're back online
    if (navigator.onLine) {
      toast.success("Connection Restored!", { description: "You're back online." });
      navigate(-1);
    } else {
      setTimeout(() => {
        setIsRetrying(false);
        toast.error("Still Offline", { description: "Please check your internet connection." });
      }, 2000);
    }
  };

  return (
    <ErrorLayout>
      <Card className="border-border/50">
        <CardContent className="pt-8 pb-8 space-y-6">
          <div className="w-16 h-16 mx-auto rounded-full bg-muted flex items-center justify-center">
            <WifiOff className="w-8 h-8 text-muted-foreground" />
          </div>

          <div className="space-y-2">
            <h1 className="text-2xl font-semibold text-foreground">No Internet Connection</h1>
            <p className="text-muted-foreground">
              Please check your connection and try again.
            </p>
          </div>

          <div className="flex flex-col gap-3">
            <Button 
              size="lg" 
              className="w-full gap-2" 
              onClick={handleRetry}
              disabled={isRetrying}
            >
              {isRetrying ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Checking...
                </>
              ) : (
                "Retry"
              )}
            </Button>
          </div>

          <p className="text-xs text-muted-foreground">
            This page will auto-recover when connection is restored.
          </p>
        </CardContent>
      </Card>
    </ErrorLayout>
  );
};

export default NetworkErrorPage;
