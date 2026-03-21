// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Loader2, ArrowLeft, Mail, Info } from "lucide-react";
import { authApi } from "@/services/api";

interface ForgotPasswordFormProps {
  onBackToLogin: () => void;
}

const ForgotPasswordForm = ({ onBackToLogin }: ForgotPasswordFormProps) => {
  const [email, setEmail] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!email) {
      setError("Please enter your email address");
      return;
    }

    setIsLoading(true);
    try {
      await authApi.requestPasswordReset(email);
      setSubmitted(true);
    } catch {
      // Always show success to prevent email enumeration
      setSubmitted(true);
    } finally {
      setIsLoading(false);
    }
  };

  if (submitted) {
    return (
      <div className="space-y-6">
        <div className="text-center">
          <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center mx-auto mb-4">
            <Mail size={24} className="text-primary" aria-hidden="true" />
          </div>
          <h2 className="text-xl font-semibold text-foreground mb-2">Check your email</h2>
          <p className="text-muted-foreground text-sm">
            If an account with <span className="font-medium text-foreground">{email}</span> exists, a password reset link has been sent.
          </p>
        </div>

        <Alert className="border-muted">
          <Info size={16} aria-hidden="true" />
          <AlertDescription className="text-xs text-muted-foreground">
            Your administrator must configure an SMTP server for password reset emails to be delivered.
          </AlertDescription>
        </Alert>

        <Button
          variant="outline"
          className="w-full"
          onClick={onBackToLogin}
        >
          <ArrowLeft size={16} aria-hidden="true" />
          Back to sign in
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="text-center">
        <h2 className="text-xl font-semibold text-foreground mb-1">Reset password</h2>
        <p className="text-muted-foreground text-sm">
          Enter your email and we'll send you a reset link
        </p>
      </div>

      <Alert className="border-muted">
        <Info size={16} />
        <AlertDescription className="text-xs text-muted-foreground">
          Password reset requires an SMTP server to be configured by your administrator.
        </AlertDescription>
      </Alert>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="reset-email" className="text-foreground/90">
            Email
          </Label>
          <Input
            id="reset-email"
            type="email"
            placeholder="you@company.com"
            aria-label="Email address"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            autoFocus
          />
        </div>

        {error && (
          <div role="alert" className="text-destructive text-sm bg-destructive/10 p-3 rounded-lg border border-destructive/20">
            {error}
          </div>
        )}

        <Button
          type="submit"
          className="w-full bg-gradient-to-r from-primary to-accent hover:opacity-90"
          size="lg"
          disabled={isLoading}
        >
          {isLoading ? (
            <>
              <Loader2 className="motion-safe:animate-spin" aria-hidden="true" />
              Sending...
            </>
          ) : (
            "Send reset link"
          )}
        </Button>
      </form>

      <div className="text-center">
        <button
          type="button"
          onClick={onBackToLogin}
          className="text-sm text-muted-foreground hover:text-primary transition-colors inline-flex items-center gap-1"
        >
          <ArrowLeft size={14} aria-hidden="true" />
          Back to sign in
        </button>
      </div>
    </div>
  );
};

export default ForgotPasswordForm;
