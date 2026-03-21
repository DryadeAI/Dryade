// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { Outlet, Navigate, useLocation, Link } from "react-router-dom";
import { usePreferences } from "@/hooks/usePreferences";
import { lazy, Suspense, useState, useEffect, useCallback } from "react";
import KeyboardShortcutsDialog from "@/components/shared/KeyboardShortcutsDialog";
import { useTranslation } from "react-i18next";
import { Menu } from "lucide-react";
import { Button } from "@/components/ui/button";
import iconLogo from "@/assets/icon-logo.svg";

import BlurryBackground from "@/components/shared/BlurryBackground";

// Lazy load AppSidebar to prevent module-level router hook execution
const AppSidebar = lazy(() => import("./AppSidebar"));

// Shared mobile open state is lifted into WorkspaceLayout so the top bar
// hamburger can trigger the sidebar that lives inside AppSidebar.
// AppSidebar reads this via a prop when provided; it falls back to its own
// internal state for backward compatibility.
const WorkspaceLayout = () => {
  const location = useLocation();
  const { preferences } = usePreferences();
  const { t } = useTranslation();
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  // Close mobile sidebar on route change
  useEffect(() => {
    setMobileSidebarOpen(false);
  }, [location.pathname]);

  // Global keyboard shortcut for help dialog
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "/") {
        e.preventDefault();
        setShortcutsOpen((prev) => !prev);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const openMobileSidebar = useCallback(() => setMobileSidebarOpen(true), []);

  // Redirect /workspace root to the user's preferred default view
  if (location.pathname === "/workspace") {
    const defaultPath = preferences.defaultView === "chat"
      ? "/workspace/chat"
      : preferences.defaultView === "dashboard"
      ? "/workspace/dashboard"
      : "/workspace/workflows";

    return <Navigate to={defaultPath} replace />;
  }

  return (
    <>
      {/* Skip to content link for keyboard navigation */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 focus:px-4 focus:py-2 focus:bg-primary focus:text-primary-foreground focus:rounded-md focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
      >
        Skip to main content
      </a>

      <BlurryBackground />

      {/* Mobile top bar — sticky header on small screens with hamburger + logo */}
      <header className="md:hidden sticky top-0 z-40 flex items-center justify-between px-4 py-3 bg-sidebar border-b border-border/40 min-h-[52px]">
        <Button
          variant="ghost"
          size="icon"
          className="min-h-[44px] min-w-[44px]"
          onClick={openMobileSidebar}
          aria-label={t('actions.openMenu', 'Open menu')}
          aria-expanded={mobileSidebarOpen}
          aria-controls="mobile-sidebar"
        >
          <Menu size={20} aria-hidden="true" />
        </Button>
        <Link to="/workspace" className="flex items-center gap-2 absolute left-1/2 -translate-x-1/2">
          <img src={iconLogo} alt="Dryade" className="w-7 h-7 dark:brightness-100 brightness-0" />
          <span className="font-semibold text-sm text-sidebar-foreground">
            Dryade<span className="text-primary">App</span>
          </span>
        </Link>
        {/* Spacer to balance hamburger */}
        <div className="w-[44px]" aria-hidden="true" />
      </header>

      <div className="flex h-[calc(100vh-52px)] md:h-screen overflow-hidden">
        <Suspense fallback={<div className="w-56 h-screen bg-sidebar border-r border-sidebar-border hidden md:flex" />}>
          <AppSidebar externalMobileOpen={mobileSidebarOpen} onExternalMobileClose={() => setMobileSidebarOpen(false)} />
        </Suspense>
        <main id="main-content" tabIndex={-1} className="flex-1 overflow-auto focus:outline-none">
          <div key={location.pathname} className="animate-fade-in h-full">
            <Outlet />
          </div>
        </main>
      </div>
      <KeyboardShortcutsDialog open={shortcutsOpen} onOpenChange={setShortcutsOpen} />
    </>
  );
};

export default WorkspaceLayout;
