// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useEffect } from "react";
import iconLogo from "@/assets/icon-logo.svg";
import LoginForm from "@/components/auth/LoginForm";
import RegisterForm from "@/components/auth/RegisterForm";
import ForgotPasswordForm from "@/components/auth/ForgotPasswordForm";
import { authApi } from "@/services/api";
type AuthView = "login" | "register" | "forgot-password";
const AuthPage = () => {
  const [view, setView] = useState<AuthView>("login");
  const [hasSsoPlugin, setHasSsoPlugin] = useState(false);
  const [ssoLoading, setSsoLoading] = useState(true);
  useEffect(() => {
    authApi.checkPlugins().then(result => {
      setHasSsoPlugin(result?.plugins?.includes("zitadel_auth") ?? false);
    }).catch(() => {
      setHasSsoPlugin(false);
    }).finally(() => setSsoLoading(false));

    // Fallback: if checkPlugins hangs, stop loading after 3s
    const timeout = setTimeout(() => setSsoLoading(false), 3000);
    return () => clearTimeout(timeout);
  }, []);
  return <div className="min-h-screen flex items-center justify-center p-4 relative bg-background dark:bg-transparent" style={{
    // Dark theme gets the atmospheric forest gradients; light theme uses bg-background from CSS
  }}>
    {/* Dark-only atmospheric background */}
    <div className="absolute inset-0 hidden dark:block" style={{
      background: `
        radial-gradient(ellipse 80% 60% at 20% 80%, rgba(13,37,25,0.6) 0%, transparent 60%),
        radial-gradient(ellipse 60% 50% at 80% 20%, rgba(16,39,29,0.4) 0%, transparent 50%),
        radial-gradient(ellipse 40% 40% at 50% 50%, rgba(36,143,48,0.05) 0%, transparent 60%),
        radial-gradient(ellipse 100% 100% at 50% 100%, rgba(3,15,11,0.9) 0%, transparent 70%),
        linear-gradient(180deg, #020A07 0%, #030F0B 40%, #0A2A1F 80%, #061A13 100%)
      `
    }} />
      {/* Subtle floating orbs — dark only */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden hidden dark:block">
        <div className="absolute top-1/4 left-1/5 w-72 h-72 bg-primary/[0.04] rounded-full blur-3xl motion-safe:animate-pulse" style={{
        animationDuration: "8s"
      }} />
        <div className="absolute bottom-1/3 right-1/5 w-64 h-64 bg-accent/[0.03] rounded-full blur-3xl motion-safe:animate-pulse" style={{
        animationDuration: "12s"
      }} />
        <div className="absolute top-2/3 left-1/2 w-96 h-96 bg-secondary/[0.06] rounded-full blur-3xl motion-safe:animate-pulse" style={{
        animationDuration: "10s"
      }} />
      </div>

      <div className="w-full max-w-md relative z-10">
        {/* Logo — subtle glow, not overpowering */}
        <div className="text-center mb-8 motion-safe:animate-fade-in relative">
          <div className="absolute inset-0 hidden dark:flex items-center justify-center">
            <div className="w-32 h-32 rounded-full bg-emerald-500/20 blur-2xl" />
          </div>
          <img src={iconLogo} alt="Dryade" className="h-24 mx-auto dark:brightness-100 brightness-0 relative" style={{ filter: 'drop-shadow(0 0 20px rgba(90,205,102,0.6)) drop-shadow(0 0 60px rgba(90,205,102,0.3))' }} />
        </div>

        {/* Auth Card — the only light source in the void */}
        <div className="border border-border/30 rounded-xl p-8 shadow-xl motion-safe:animate-slide-up bg-forest-950">
          {ssoLoading ? <div className="flex items-center justify-center py-8">
              <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full motion-safe:animate-spin" />
            </div> : view === "login" ? <LoginForm onSwitchToRegister={() => setView("register")} onForgotPassword={() => setView("forgot-password")} hasSsoPlugin={hasSsoPlugin} /> : view === "register" ? <RegisterForm onSwitchToLogin={() => setView("login")} /> : <ForgotPasswordForm onBackToLogin={() => setView("login")} />}
        </div>

        {/* Footer */}
        <div className="mt-6 text-center text-xs text-muted-foreground motion-safe:animate-fade-in">
          <p>Air-gapped • Standards-native • Sovereign</p>
        </div>
      </div>
    </div>;
};
export default AuthPage;