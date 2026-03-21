// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Eye, EyeOff, Loader2, ArrowRight, Check, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { authApi } from "@/services/api";
import { usePreferences } from "@/hooks/usePreferences";

interface RegisterFormProps {
  onSwitchToLogin: () => void;
}

type PasswordStrength = 'weak' | 'fair' | 'good' | 'strong';

const RegisterForm = ({ onSwitchToLogin }: RegisterFormProps) => {
  const navigate = useNavigate();
  const { t } = useTranslation('auth');
  const { preferences } = usePreferences();
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");

  const passwordCriteria = useMemo(() => ({
    minLength: password.length >= 8,
    hasUpperCase: /[A-Z]/.test(password),
    hasLowerCase: /[a-z]/.test(password),
    hasNumber: /\d/.test(password),
    hasSpecial: /[!@#$%^&*]/.test(password),
  }), [password]);

  const passwordStrength = useMemo((): PasswordStrength => {
    const met = Object.values(passwordCriteria).filter(Boolean).length;
    if (met <= 1) return 'weak';
    if (met <= 2) return 'fair';
    if (met <= 4) return 'good';
    return 'strong';
  }, [passwordCriteria]);

  const strengthConfig = {
    weak: { color: 'bg-destructive', labelKey: 'password.weak', bars: 1 },
    fair: { color: 'bg-warning', labelKey: 'password.fair', bars: 2 },
    good: { color: 'bg-primary', labelKey: 'password.good', bars: 3 },
    strong: { color: 'bg-success', labelKey: 'password.strong', bars: 4 },
  };

  const passwordsMatch = password === confirmPassword && confirmPassword.length > 0;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!email || !password || !confirmPassword) {
      setError(t('errors.fillRequired'));
      return;
    }

    if (password.length < 8) {
      setError(t('errors.passwordMin'));
      return;
    }

    if (password !== confirmPassword) {
      setError(t('errors.passwordsNoMatch'));
      return;
    }

    setIsLoading(true);

    try {
      await authApi.register({ email, password, display_name: displayName || undefined });
      navigate(`/workspace/${preferences.defaultView}`);
    } catch (err: unknown) {
      if (err instanceof Error) {
        if (err.message.includes('404')) {
          setError(t('errors.registrationUnavailable'));
        } else {
          setError(err.message || t('errors.registrationFailed'));
        }
      } else {
        setError(t('errors.registrationFailed'));
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="text-center">
        <h2 className="text-xl font-semibold text-foreground mb-1">{t('register.title')}</h2>
        <p className="text-muted-foreground text-sm">{t('register.subtitle')}</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="reg-email" className="text-foreground/90">{t('register.email')}</Label>
          <Input
            id="reg-email"
            type="email"
            placeholder={t('login.emailPlaceholder')}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            autoFocus
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="display-name" className="text-foreground/90">
            {t('register.displayName')} <span className="text-muted-foreground text-xs">{t('register.displayNameOptional')}</span>
          </Label>
          <Input
            id="display-name"
            type="text"
            placeholder={t('register.displayNamePlaceholder')}
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            maxLength={100}
          />
          {displayName.length > 80 && (
            <p className="text-xs text-muted-foreground text-right">
              {displayName.length}/100
            </p>
          )}
        </div>

        <div className="space-y-2">
          <Label htmlFor="reg-password" className="text-foreground/90">{t('register.password')}</Label>
          <div className="relative">
            <Input
              id="reg-password"
              type={showPassword ? "text" : "password"}
              placeholder={t('register.passwordPlaceholder')}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
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

          {password.length > 0 && (
            <div className="space-y-2">
              <div className="flex gap-1 h-1">
                {[1, 2, 3, 4].map((bar) => (
                  <div
                    key={bar}
                    className={cn(
                      "flex-1 rounded-full transition-colors",
                      bar <= strengthConfig[passwordStrength].bars
                        ? strengthConfig[passwordStrength].color
                        : "bg-muted"
                    )}
                  />
                ))}
              </div>
              <p className={cn(
                "text-xs",
                passwordStrength === 'weak' && "text-destructive",
                passwordStrength === 'fair' && "text-warning",
                passwordStrength === 'good' && "text-primary",
                passwordStrength === 'strong' && "text-success"
              )}>
                {t(strengthConfig[passwordStrength].labelKey)}
              </p>

              <div className="grid grid-cols-2 gap-1 text-xs">
                {[
                  { key: 'minLength', labelKey: 'password.minLength' },
                  { key: 'hasUpperCase', labelKey: 'password.uppercase' },
                  { key: 'hasLowerCase', labelKey: 'password.lowercase' },
                  { key: 'hasNumber', labelKey: 'password.numbers' },
                  { key: 'hasSpecial', labelKey: 'password.special' },
                ].map(({ key, labelKey }) => (
                  <div
                    key={key}
                    className={cn(
                      "flex items-center gap-1",
                      passwordCriteria[key as keyof typeof passwordCriteria]
                        ? "text-success"
                        : "text-muted-foreground"
                    )}
                  >
                    {passwordCriteria[key as keyof typeof passwordCriteria] ? (
                      <Check size={12} />
                    ) : (
                      <X size={12} />
                    )}
                    {t(labelKey)}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="space-y-2">
          <Label htmlFor="confirm-password" className="text-foreground/90">{t('register.confirmPassword')}</Label>
          <div className="relative">
            <Input
              id="confirm-password"
              type={showConfirmPassword ? "text" : "password"}
              placeholder={t('register.confirmPasswordPlaceholder')}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              autoComplete="new-password"
              className="pr-10"
            />
            <button
              type="button"
              onClick={() => setShowConfirmPassword(!showConfirmPassword)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
              aria-label={showConfirmPassword ? t('login.hidePassword') : t('login.showPassword')}
            >
              {showConfirmPassword ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </div>
          {confirmPassword.length > 0 && (
            <div className={cn(
              "flex items-center gap-1 text-xs",
              passwordsMatch ? "text-success" : "text-destructive"
            )}>
              {passwordsMatch ? <Check size={12} /> : <X size={12} />}
              {passwordsMatch ? t('register.passwordsMatch') : t('register.passwordsNoMatch')}
            </div>
          )}
        </div>

        {error && (
          <div
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
          data-testid="auth-register-submit"
        >
          {isLoading ? (
            <>
              <Loader2 className="animate-spin" />
              {t('register.submitting')}
            </>
          ) : (
            <>
              {t('register.submit')}
              <ArrowRight size={18} />
            </>
          )}
        </Button>
      </form>

      <div className="text-center">
        <button
          type="button"
          onClick={onSwitchToLogin}
          className="text-sm text-muted-foreground hover:text-primary transition-colors"
        >
          {t('register.hasAccount')}
        </button>
      </div>
    </div>
  );
};

export default RegisterForm;
