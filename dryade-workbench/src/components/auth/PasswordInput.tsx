// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useMemo } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Eye, EyeOff, Check, X } from "lucide-react";
import { cn } from "@/lib/utils";

type PasswordStrength = "weak" | "fair" | "good" | "strong";

interface PasswordInputProps {
  id: string;
  value: string;
  onChange: (value: string) => void;
  label?: string;
  placeholder?: string;
  showStrength?: boolean;
  showCriteria?: boolean;
  autoComplete?: string;
  className?: string;
}

const strengthConfig: Record<PasswordStrength, { color: string; label: string; bars: number }> = {
  weak: { color: "bg-destructive", label: "Weak", bars: 1 },
  fair: { color: "bg-warning", label: "Fair", bars: 2 },
  good: { color: "bg-primary", label: "Good", bars: 3 },
  strong: { color: "bg-success", label: "Strong", bars: 4 },
};

const PasswordInput = ({
  id,
  value,
  onChange,
  label = "Password",
  placeholder = "Enter password",
  showStrength = true,
  showCriteria = true,
  autoComplete = "current-password",
  className,
}: PasswordInputProps) => {
  const [showPassword, setShowPassword] = useState(false);

  const criteria = useMemo(
    () => ({
      minLength: value.length >= 8,
      hasUpperCase: /[A-Z]/.test(value),
      hasLowerCase: /[a-z]/.test(value),
      hasNumber: /\d/.test(value),
      hasSpecial: /[!@#$%^&*]/.test(value),
    }),
    [value]
  );

  const strength = useMemo((): PasswordStrength => {
    const met = Object.values(criteria).filter(Boolean).length;
    if (met <= 1) return "weak";
    if (met <= 2) return "fair";
    if (met <= 4) return "good";
    return "strong";
  }, [criteria]);

  return (
    <div className={cn("space-y-2", className)}>
      {label && (
        <Label htmlFor={id} className="text-foreground/90">
          {label}
        </Label>
      )}
      <div className="relative">
        <Input
          id={id}
          type={showPassword ? "text" : "password"}
          placeholder={placeholder}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          autoComplete={autoComplete}
          className="pr-10"
        />
        <button
          type="button"
          onClick={() => setShowPassword(!showPassword)}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
          aria-label={showPassword ? "Hide password" : "Show password"}
        >
          {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
        </button>
      </div>

      {value.length > 0 && showStrength && (
        <div className="space-y-2">
          {/* Strength bars */}
          <div className="flex gap-1 h-1">
            {[1, 2, 3, 4].map((bar) => (
              <div
                key={bar}
                className={cn(
                  "flex-1 rounded-full transition-colors",
                  bar <= strengthConfig[strength].bars
                    ? strengthConfig[strength].color
                    : "bg-muted"
                )}
              />
            ))}
          </div>
          <p
            className={cn(
              "text-xs",
              strength === "weak" && "text-destructive",
              strength === "fair" && "text-warning",
              strength === "good" && "text-primary",
              strength === "strong" && "text-success"
            )}
          >
            {strengthConfig[strength].label}
          </p>

          {/* Criteria checklist */}
          {showCriteria && (
            <div className="grid grid-cols-2 gap-1 text-xs">
              {[
                { key: "minLength", label: "8+ characters" },
                { key: "hasUpperCase", label: "Uppercase" },
                { key: "hasLowerCase", label: "Lowercase" },
                { key: "hasNumber", label: "Numbers" },
                { key: "hasSpecial", label: "Special (!@#$%)" },
              ].map(({ key, label }) => (
                <div
                  key={key}
                  className={cn(
                    "flex items-center gap-1",
                    criteria[key as keyof typeof criteria]
                      ? "text-success"
                      : "text-muted-foreground"
                  )}
                >
                  {criteria[key as keyof typeof criteria] ? (
                    <Check size={12} />
                  ) : (
                    <X size={12} />
                  )}
                  {label}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default PasswordInput;
