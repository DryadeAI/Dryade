// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useLocalStorage } from "@/hooks/useLocalStorage";
import { useLocation } from "react-router-dom";
import { useEffect, useCallback } from "react";

export type SidebarMode = "main" | "chat" | "plans";

interface UseSidebarModeReturn {
  mode: SidebarMode;
  setMode: (mode: SidebarMode) => void;
  returnToMain: () => void;
}

/**
 * Hook to manage the sidebar mode (main navigation vs context-specific).
 * Auto-detects mode based on current route and persists to localStorage.
 */
export const useSidebarMode = (): UseSidebarModeReturn => {
  const location = useLocation();
  const [mode, setModeInternal] = useLocalStorage<SidebarMode>("sidebar-mode", "main");

  // Auto-detect mode from route
  useEffect(() => {
    const path = location.pathname;
    
    if (path.startsWith("/workspace/chat")) {
      setModeInternal("chat");
    } else if (path.startsWith("/workspace/plans")) {
      setModeInternal("plans");
    }
    // Don't auto-switch to main when navigating away - let the back button handle that
  }, [location.pathname, setModeInternal]);

  const setMode = useCallback((newMode: SidebarMode) => {
    setModeInternal(newMode);
  }, [setModeInternal]);

  const returnToMain = useCallback(() => {
    setModeInternal("main");
  }, [setModeInternal]);

  return { mode, setMode, returnToMain };
};
