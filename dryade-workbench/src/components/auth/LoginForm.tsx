// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Eye, EyeOff, Loader2, ArrowRight, Building } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { usePreferences } from "@/hooks/usePreferences";

interface LoginFormProps {
  onSwitchToRegister: () => void;
  onForgotPassword?: () => void;
  hasSsoPlugin?: boolean;
}

const LoginForm = ({ onSwitchToRegister, onForgotPassword, hasSsoPlugin = false }: LoginFormProps) => {
  const navigate = useNavigate();
  const { t } = useTranslation('auth');
  const { login } = useAuth();
  const { preferences } = usePreferences();
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!email || !password) {
      setError(t('errors.fillAllFields'));
      return;
    }

    if (password.length < 8) {
      setError(t('errors.passwordMin'));
      return;
    }

    setIsLoading(true);

    try {
      await login({ email, password });
      navigate(`/workspace/${preferences.defaultView}`);
    } catch (err) {
      setError(t('errors.invalidCredentials'));
    } finally {
      setIsLoading(false);
    }
  };

  const handleSsoLogin = async () => {
    console.log("SSO login initiated");
  };

  return (
    <div className="space-y-6">
      <div className="text-center">
        <h2 className="text-xl font-semibold text-foreground mb-1">{t('login.title')}</h2>
        <p className="text-muted-foreground text-sm">{t('login.subtitle')}</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="email" className="text-foreground/90">{t('login.email')}</Label>
          <Input
            id="email"
            type="email"
            placeholder={t('login.emailPlaceholder')}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            autoFocus
            data-testid="auth-login-email"
            aria-describedby={error ? "login-error" : undefined}
            aria-invalid={!!error}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="password" className="text-foreground/90">{t('login.password')}</Label>
          <div className="relative">
            <Input
              id="password"
              type={showPassword ? "text" : "password"}
              placeholder={t('login.passwordPlaceholder')}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              data-testid="auth-login-password"
              className="pr-10"
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
              aria-label={showPassword ? t('login.hidePassword') : t('login.showPassword')}
            >
              {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </div>
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Checkbox
              id="remember"
              checked={rememberMe}
              onCheckedChange={(checked) => setRememberMe(checked === true)}
            />
            <Label htmlFor="remember" className="text-sm text-muted-foreground cursor-pointer">
              {t('login.rememberMe')}
            </Label>
          </div>
          <button
            type="button"
            className="text-sm text-muted-foreground hover:text-primary transition-colors"
            onClick={onForgotPassword}
          >
            {t('login.forgotPassword')}
          </button>
        </div>

        {error && (
          <div
            id="login-error"
            role="alert"
            className="text-destructive text-sm bg-destructive/10 p-3 rounded-lg border border-destructive/20"
          >
            {error}
          </div>
        )}

        <Button
          type="submit"
          className="w-full bg-gradient-to-r from-primary to-accent hover:opacity-90"
          size="lg"
          disabled={isLoading}
          data-testid="auth-login-submit"
        >
          {isLoading ? (
            <>
              <Loader2 className="animate-spin" />
              {t('login.submitting')}
            </>
          ) : (
            <>
              {t('login.submit')}
              <ArrowRight size={18} />
            </>
          )}
        </Button>
      </form>

      {hasSsoPlugin && (
        <>
          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-border" />
            </div>
            <div className="relative flex justify-center text-xs uppercase">
              <span className="bg-card px-2 text-muted-foreground">{t('login.orContinueWith')}</span>
            </div>
          </div>

          <Button variant="outline" className="w-full" onClick={handleSsoLogin}>
            <Building size={18} />
            {t('login.sso')}
            <span className="ml-auto text-xs bg-primary/10 text-primary px-2 py-0.5 rounded-full">
              {t('login.enterprise')}
            </span>
          </Button>
        </>
      )}

      <div className="text-center">
        <button
          type="button"
          onClick={onSwitchToRegister}
          className="text-sm text-muted-foreground hover:text-primary transition-colors"
          data-testid="auth-register-link"
        >
          {t('login.noAccount')}
        </button>
      </div>
    </div>
  );
};

export default LoginForm;
