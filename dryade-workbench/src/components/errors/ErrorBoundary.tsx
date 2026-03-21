// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import React, { Component, ErrorInfo, ReactNode } from "react";
import { AlertTriangle, RefreshCw, Home } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
    errorInfo: null,
  };

  public static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("ErrorBoundary caught an error:", error, errorInfo);
    this.setState({ errorInfo });
  }

  private handleRetry = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
  };

  private handleGoHome = () => {
    window.location.href = "/workspace/dashboard";
  };

  public render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="min-h-screen bg-background flex items-center justify-center p-6">
          <Card className="w-full max-w-md border-border/50">
            <CardContent className="pt-8 pb-8 space-y-6 text-center">
              <div className="w-16 h-16 mx-auto rounded-full bg-destructive/10 flex items-center justify-center">
                <AlertTriangle className="w-8 h-8 text-destructive" />
              </div>

              <div className="space-y-2">
                <h1 className="text-2xl font-semibold text-foreground">
                  Something Went Wrong
                </h1>
                <p className="text-muted-foreground">
                  An unexpected error occurred in this component.
                </p>
              </div>

              {this.state.error && (
                <div className="bg-muted/50 rounded-lg p-4 text-left text-sm overflow-auto max-h-32">
                  <code className="text-destructive text-xs">
                    {this.state.error.message}
                  </code>
                </div>
              )}

              <div className="flex flex-col gap-3">
                <Button
                  size="lg"
                  className="w-full gap-2"
                  onClick={this.handleRetry}
                >
                  <RefreshCw className="w-4 h-4" />
                  Try Again
                </Button>
                <Button
                  variant="outline"
                  size="lg"
                  className="w-full gap-2"
                  onClick={this.handleGoHome}
                >
                  <Home className="w-4 h-4" />
                  Go to Dashboard
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
