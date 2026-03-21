// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import React, { Suspense, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate, useParams } from "react-router-dom";
import { ThemeProvider } from "next-themes";
import { PreferencesProvider } from "@/hooks/usePreferences";
import { AuthProvider } from "@/contexts/AuthContext";
import { MockDataProvider } from "@/mocks/MockDataProvider";
import ErrorBoundary from "@/components/errors/ErrorBoundary";
import { rtlLanguages } from "@/i18n";
import { ErrorBoundary as PageErrorBoundary } from "react-error-boundary";
import type { FallbackProps } from "react-error-boundary";
import RouteAnnouncer from "@/components/shared/RouteAnnouncer";
import AuthGuard from "./components/auth/AuthGuard";
import OnboardingGuard from "./components/onboarding/OnboardingGuard";
import WorkspaceLayout from "./components/layout/WorkspaceLayout";
import { Button } from "@/components/ui/button";
import { Loader2 } from "lucide-react";
import PWAInstallPrompt from "@/components/pwa/PWAInstallPrompt";
import PWAUpdatePrompt from "@/components/pwa/PWAUpdatePrompt";

// Retry wrapper for React.lazy — prevents permanent failure on transient import errors
function lazyRetry<T extends React.ComponentType<unknown>>(
  factory: () => Promise<{ default: T }>,
  retries = 3,
): React.LazyExoticComponent<T> {
  return React.lazy(() =>
    factory().catch((err) => {
      if (retries <= 0) throw err;
      return new Promise<{ default: T }>((resolve) =>
        setTimeout(() => resolve(lazyRetry(factory, retries - 1) as never), 1000)
      );
    })
  ) as React.LazyExoticComponent<T>;
}

// Lazy-loaded page components with retry (PERF-02)
const AuthPage = lazyRetry(() => import("./pages/AuthPage"));
const DashboardPage = lazyRetry(() => import("./pages/DashboardPage"));
const ChatPage = lazyRetry(() => import("./pages/ChatPage"));
const AgentsPage = lazyRetry(() => import("./pages/AgentsPage"));
const AgentDetailPage = lazyRetry(() => import("./pages/AgentDetailPage"));
const FlowDetailPage = lazyRetry(() => import("./pages/FlowDetailPage"));
const WorkflowPage = lazyRetry(() => import("./pages/WorkflowPage"));
// PlansPage removed - unified under WorkflowPage (Phase 70)
const KnowledgePage = lazyRetry(() => import("./pages/KnowledgePage"));
const HealthPage = lazyRetry(() => import("./pages/HealthPage"));
const MetricsPage = lazyRetry(() => import("./pages/MetricsPage"));
// Free-core features: native pages (Phase 191)
const CostTrackerPage = lazyRetry(() => import("./pages/CostTrackerPage"));
const ClarifyPreferencesPage = lazyRetry(() => import("./pages/ClarifyPreferencesPage"));
// FileSafetyPage moved to file_safety plugin UI
// TrainerPage and ModelsPage moved to trainer plugin UI
const LoopsPage = lazyRetry(() => import("./pages/LoopsPage"));
const PluginsPage = lazyRetry(() => import("./pages/PluginsPage"));
// ProfilePage removed - consolidated into Settings Account tab
const SettingsPage = lazyRetry(() => import("./pages/SettingsPage"));
const AdminPage = lazyRetry(() => import("./pages/AdminPage"));
const PluginUIPage = lazyRetry(() => import("./pages/PluginUIPage"));
const ExecutionAuditPage = lazyRetry(() => import("./pages/ExecutionAuditPage"));
const FactoryPage = lazyRetry(() => import("./pages/FactoryPage"));
const NotFound = lazyRetry(() => import("./pages/NotFound"));
const UnauthorizedPage = lazyRetry(() => import("./pages/errors/UnauthorizedPage"));
const ForbiddenPage = lazyRetry(() => import("./pages/errors/ForbiddenPage"));
const ServerErrorPage = lazyRetry(() => import("./pages/errors/ServerErrorPage"));
const NetworkErrorPage = lazyRetry(() => import("./pages/errors/NetworkErrorPage"));

// Shared loading fallback for Suspense boundaries
const PageLoader = () => (
  <div className="flex items-center justify-center h-screen">
    <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
  </div>
);

// Page-level error fallback for crash isolation (AP-05)
function PageErrorFallback({ error, resetErrorBoundary }: FallbackProps) {
  const message = error instanceof Error ? error.message : "An unexpected error occurred";
  return (
    <div className="flex flex-col items-center justify-center h-screen gap-4">
      <h2 className="text-xl font-semibold">Something went wrong</h2>
      <p className="text-muted-foreground">{message}</p>
      <Button onClick={resetErrorBoundary}>Try again</Button>
    </div>
  );
}

// Wraps a lazy page component with ErrorBoundary + Suspense for crash isolation
function PageWrapper({ children }: { children: React.ReactNode }) {
  return (
    <PageErrorBoundary FallbackComponent={PageErrorFallback}>
      <Suspense fallback={<PageLoader />}>
        {children}
      </Suspense>
    </PageErrorBoundary>
  );
}

const queryClient = new QueryClient();

// Redirect /workspace/plans/:id to /workspace/workflows?planId=:id
const PlanRedirect = () => {
  const { id } = useParams<{ id: string }>();
  return <Navigate to={`/workspace/workflows?planId=${id}`} replace />;
};

const App = () => {
  const { i18n } = useTranslation();

  // Set lang and dir attributes on <html> when language changes
  useEffect(() => {
    const lang = i18n.language;
    document.documentElement.lang = lang;
    document.documentElement.dir = rtlLanguages.includes(lang) ? 'rtl' : 'ltr';
  }, [i18n.language]);

  return (
  <ErrorBoundary>
    <QueryClientProvider client={queryClient}>
      <ThemeProvider attribute="class" defaultTheme="dark" enableSystem>
        <MockDataProvider>
        <AuthProvider>
          <PreferencesProvider>
            <TooltipProvider>
            <Toaster />
            <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
              <RouteAnnouncer />
              <Routes>
                <Route path="/" element={<Navigate to="/auth" replace />} />
                <Route path="/auth" element={<PageWrapper><AuthPage /></PageWrapper>} />
                <Route path="/workspace" element={<AuthGuard><OnboardingGuard><WorkspaceLayout /></OnboardingGuard></AuthGuard>}>
                  <Route index element={<Navigate to="dashboard" replace />} />
                  <Route path="dashboard" element={<PageWrapper><DashboardPage /></PageWrapper>} />
                  {/* Executions - audit page for reviewing past workflow runs */}
                  <Route path="executions" element={<Navigate to="/workspace/dashboard" replace />} />
                  <Route path="executions/:executionId" element={<PageWrapper><ExecutionAuditPage /></PageWrapper>} />
                  <Route path="chat" element={<PageWrapper><ChatPage /></PageWrapper>} />
                  <Route path="chat/:id" element={<PageWrapper><ChatPage /></PageWrapper>} />
                  <Route path="agents" element={<PageWrapper><AgentsPage /></PageWrapper>} />
                  <Route path="agents/:name" element={<PageWrapper><AgentDetailPage /></PageWrapper>} />
                  {/* Unified Workflows - Flows route redirects to workflows */}
                  <Route path="flows" element={<Navigate to="/workspace/workflows" replace />} />
                  <Route path="flows/:id" element={<PageWrapper><FlowDetailPage /></PageWrapper>} />
                  <Route path="workflows" element={<PageWrapper><WorkflowPage /></PageWrapper>} />
                  <Route path="workflows/:id" element={<PageWrapper><WorkflowPage /></PageWrapper>} />
                  {/* Plans routes redirect to unified Workflows (Phase 70) */}
                  <Route path="plans" element={<Navigate to="/workspace/workflows" replace />} />
                  <Route path="plans/:id" element={<PlanRedirect />} />
                  <Route path="knowledge" element={<PageWrapper><KnowledgePage /></PageWrapper>} />
                  <Route path="factory" element={<PageWrapper><FactoryPage /></PageWrapper>} />
                  <Route path="loops" element={<PageWrapper><LoopsPage /></PageWrapper>} />
                  <Route path="health" element={<PageWrapper><HealthPage /></PageWrapper>} />
                  <Route path="metrics" element={<PageWrapper><MetricsPage /></PageWrapper>} />
                  {/* Free-core features: native pages (Phase 191) */}
                  <Route path="cost-tracker" element={<PageWrapper><CostTrackerPage /></PageWrapper>} />
                  <Route path="costs" element={<Navigate to="/workspace/cost-tracker" replace />} />
                  <Route path="clarify-preferences" element={<PageWrapper><ClarifyPreferencesPage /></PageWrapper>} />
                  <Route path="files" element={<Navigate to="/workspace/plugins/file_safety" replace />} />
                  <Route path="plugins" element={<PageWrapper><PluginsPage /></PageWrapper>} />
                  {/* Dynamic plugin UI routes - catches /workspace/plugins/:pluginName */}
                  <Route path="plugins/:pluginName" element={<PageWrapper><PluginUIPage /></PageWrapper>} />
                  {/* Enterprise trainer - served via plugin UI system */}
                  <Route path="trainer" element={<Navigate to="/workspace/plugins/trainer" replace />} />
                  <Route path="models" element={<Navigate to="/workspace/plugins/trainer" replace />} />
                  {/* Profile consolidated into Settings Account tab */}
                  <Route path="profile" element={<Navigate to="/workspace/settings" replace />} />
                  <Route path="settings" element={<PageWrapper><SettingsPage /></PageWrapper>} />
                  <Route path="admin" element={<PageWrapper><AdminPage /></PageWrapper>} />
                </Route>
                <Route path="/401" element={<PageWrapper><UnauthorizedPage /></PageWrapper>} />
                <Route path="/403" element={<PageWrapper><ForbiddenPage /></PageWrapper>} />
                <Route path="/500" element={<PageWrapper><ServerErrorPage /></PageWrapper>} />
                <Route path="/network-error" element={<PageWrapper><NetworkErrorPage /></PageWrapper>} />
                <Route path="*" element={<PageWrapper><NotFound /></PageWrapper>} />
              </Routes>
            </BrowserRouter>
            <PWAUpdatePrompt />
            <PWAInstallPrompt />
            </TooltipProvider>
          </PreferencesProvider>
        </AuthProvider>
        </MockDataProvider>
      </ThemeProvider>
    </QueryClientProvider>
  </ErrorBoundary>
  );
};

export default App;
