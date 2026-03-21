// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from "react";
import { z } from "zod";
import { toast } from "sonner";

export type Theme = "light" | "dark" | "system";
export type DefaultView = "dashboard" | "chat" | "agents" | "workflows" | "plans" | "knowledge";
export type AutosaveInterval = "1s" | "5s" | "manual";

// Phase 67: Agent run preferences
export type ToolCallDisplay = "collapsed" | "expanded" | "smart-collapse";

export interface AgentRunPreferences {
  toolCallDisplay: ToolCallDisplay;
  smartCollapseThreshold: number; // lines before collapsing
  showTimestamps: boolean;
  showRawOutput: boolean;
  autoAcceptCapabilities: boolean;
  acceptAllSession: boolean; // reset per session, not persisted
}

export interface Preferences {
  theme: Theme;
  autoExpandReasoning: boolean;
  showTimestamps: boolean;
  defaultView: DefaultView;
  autosaveInterval: AutosaveInterval;
  navOrder: string[]; // ordered hrefs for main nav
  // Phase 67: Agent run preferences
  agentRuns: AgentRunPreferences;
}

export const defaultNavOrder = [
  "/workspace/chat",
  "/workspace/dashboard",
  "/workspace/agents",
  "/workspace/workflows",
  "/workspace/plans",
  "/workspace/knowledge",
];

export const defaultAgentRunPreferences: AgentRunPreferences = {
  toolCallDisplay: "smart-collapse",
  smartCollapseThreshold: 10,
  showTimestamps: true,
  showRawOutput: false,
  autoAcceptCapabilities: false,
  acceptAllSession: false,
};

export const defaultPreferences: Preferences = {
  theme: "dark",
  autoExpandReasoning: false,
  showTimestamps: true,
  defaultView: "dashboard",
  autosaveInterval: "5s",
  navOrder: defaultNavOrder,
  agentRuns: defaultAgentRunPreferences,
};

// Zod schema for validating imported settings (SEC-04)
const AgentRunPreferencesSchema = z.object({
  toolCallDisplay: z.enum(["collapsed", "expanded", "smart-collapse"]).optional(),
  smartCollapseThreshold: z.number().min(1).max(1000).optional(),
  showTimestamps: z.boolean().optional(),
  showRawOutput: z.boolean().optional(),
  autoAcceptCapabilities: z.boolean().optional(),
  acceptAllSession: z.boolean().optional(),
}).strict();

const PreferencesSchema = z.object({
  theme: z.enum(["light", "dark", "system"]).optional(),
  autoExpandReasoning: z.boolean().optional(),
  showTimestamps: z.boolean().optional(),
  defaultView: z.enum(["dashboard", "chat", "agents", "workflows", "plans", "knowledge"]).optional(),
  autosaveInterval: z.enum(["1s", "5s", "manual"]).optional(),
  navOrder: z.array(z.string()).optional(),
  agentRuns: AgentRunPreferencesSchema.optional(),
}).strict();

interface PreferencesContextValue {
  preferences: Preferences;
  updatePreference: <K extends keyof Preferences>(key: K, value: Preferences[K]) => void;
  updateAgentRunPreference: <K extends keyof AgentRunPreferences>(key: K, value: AgentRunPreferences[K]) => void;
  resetToDefaults: () => void;
  exportSettings: () => string;
  importSettings: (json: string) => boolean;
  resolvedTheme: "light" | "dark";
}

const PreferencesContext = createContext<PreferencesContextValue | null>(null);

const STORAGE_KEY = "dryade-preferences";

export const PreferencesProvider = ({ children }: { children: ReactNode }) => {
  const [preferences, setPreferences] = useState<Preferences>(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        return { ...defaultPreferences, ...JSON.parse(stored) };
      }
    } catch (e) {
      console.error("Failed to load preferences:", e);
    }
    return defaultPreferences;
  });

  const [resolvedTheme, setResolvedTheme] = useState<"light" | "dark">("dark");

  // Resolve theme based on preference and system
  useEffect(() => {
    const updateResolvedTheme = () => {
      if (preferences.theme === "system") {
        const systemDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
        setResolvedTheme(systemDark ? "dark" : "light");
      } else {
        setResolvedTheme(preferences.theme);
      }
    };

    updateResolvedTheme();

    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    mediaQuery.addEventListener("change", updateResolvedTheme);
    return () => mediaQuery.removeEventListener("change", updateResolvedTheme);
  }, [preferences.theme]);

  // Apply theme to document
  useEffect(() => {
    const root = document.documentElement;
    root.classList.remove("light", "dark");
    root.classList.add(resolvedTheme);
  }, [resolvedTheme]);

  // Persist preferences
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences));
    } catch (e) {
      console.error("Failed to save preferences:", e);
    }
  }, [preferences]);

  const updatePreference = useCallback(<K extends keyof Preferences>(
    key: K,
    value: Preferences[K]
  ) => {
    setPreferences((prev) => ({ ...prev, [key]: value }));
  }, []);

  const updateAgentRunPreference = useCallback(<K extends keyof AgentRunPreferences>(
    key: K,
    value: AgentRunPreferences[K]
  ) => {
    setPreferences((prev) => ({
      ...prev,
      agentRuns: { ...prev.agentRuns, [key]: value }
    }));
  }, []);

  const resetToDefaults = useCallback(() => {
    setPreferences(defaultPreferences);
  }, []);

  const exportSettings = useCallback((): string => {
    return JSON.stringify(preferences, null, 2);
  }, [preferences]);

  const importSettings = useCallback((json: string): boolean => {
    try {
      const raw = JSON.parse(json);

      // Validate with Zod schema (SEC-04: reject unknown keys and invalid values)
      const result = PreferencesSchema.safeParse(raw);
      if (!result.success) {
        const issues = result.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; ");
        console.error("Settings validation failed:", issues);
        toast.error("Invalid settings file: " + issues);
        return false;
      }

      const parsed = result.data;

      // Merge validated data with defaults
      const newPrefs: Preferences = {
        theme: parsed.theme ?? defaultPreferences.theme,
        autoExpandReasoning: parsed.autoExpandReasoning ?? defaultPreferences.autoExpandReasoning,
        showTimestamps: parsed.showTimestamps ?? defaultPreferences.showTimestamps,
        defaultView: parsed.defaultView ?? defaultPreferences.defaultView,
        autosaveInterval: parsed.autosaveInterval ?? defaultPreferences.autosaveInterval,
        navOrder: parsed.navOrder ?? defaultPreferences.navOrder,
        agentRuns: {
          ...defaultAgentRunPreferences,
          ...(parsed.agentRuns ?? {}),
        },
      };

      setPreferences(newPrefs);
      return true;
    } catch (e) {
      console.error("Failed to import settings:", e);
      toast.error("Failed to import settings: invalid JSON");
      return false;
    }
  }, []);

  return (
    <PreferencesContext.Provider
      value={{
        preferences,
        updatePreference,
        updateAgentRunPreference,
        resetToDefaults,
        exportSettings,
        importSettings,
        resolvedTheme,
      }}
    >
      {children}
    </PreferencesContext.Provider>
  );
};

export const usePreferences = () => {
  const context = useContext(PreferencesContext);
  if (!context) {
    throw new Error("usePreferences must be used within PreferencesProvider");
  }
  return context;
};
