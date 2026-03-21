// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useEffect, useCallback, useRef } from 'react';
import { PluginRegistry, type PluginState } from '@/plugins/PluginRegistry';
import { PluginBridge } from '@/plugins/PluginBridge';
import { pluginsApi } from '@/services/api';
import type { PluginManifest, PluginUIRoute } from '@/plugins/types/pluginManifest';
import { hasUI } from '@/plugins/types/pluginManifest';

interface UIPlugin {
  name: string;
  manifest: PluginManifest;
  routes: PluginUIRoute[];
  sidebarItem?: {
    label: string;
    icon?: string;
    parent?: string;
  };
}

interface UsePluginUIResult {
  // List of plugins with UI
  uiPlugins: UIPlugin[];
  // Loading state
  isLoading: boolean;
  // Error if discovery failed
  error: string | null;
  // Refresh plugin list
  refresh: () => Promise<void>;
  // Get routes for all UI plugins
  allRoutes: PluginUIRoute[];
  // Check if a specific plugin has UI loaded
  isPluginLoaded: (name: string) => boolean;
  // Set of plugin names that were recently added (show "NEW" badge)
  newlyAddedPlugins: Set<string>;
  // Clear the "NEW" badge for a specific plugin (called when user interacts with it)
  clearNewPlugin: (name: string) => void;
}

/**
 * Hook for discovering and tracking plugin UIs
 *
 * Usage:
 * ```tsx
 * const { uiPlugins, isLoading, allRoutes, newlyAddedPlugins, clearNewPlugin } = usePluginUI();
 *
 * // Render plugin routes
 * allRoutes.map(route => (
 *   <Route path={route.path} element={<PluginLoader pluginName={...} />} />
 * ))
 * ```
 */
export function usePluginUI(): UsePluginUIResult {
  const [uiPlugins, setUIPlugins] = useState<UIPlugin[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Set of plugin names added since last reload — drives the "NEW" badge in sidebar
  const [newlyAddedPlugins, setNewlyAddedPlugins] = useState<Set<string>>(new Set());
  // Track current plugin names for diff computation
  const prevPluginNamesRef = useRef<Set<string>>(new Set());
  // Skip diff on the initial load (all plugins would otherwise be "new")
  const isFirstLoadRef = useRef(true);

  // Initialize bridge on first mount
  useEffect(() => {
    PluginBridge.initialize();
    return () => PluginBridge.destroy();
  }, []);

  // Subscribe to registry changes
  useEffect(() => {
    return PluginRegistry.subscribe(() => {
      // Force re-render when registry changes
      setUIPlugins(prev => [...prev]);
    });
  }, []);

  /**
   * Handle plugins being revoked from the allowlist.
   * Removes them from the active list and clears their "NEW" badge.
   */
  const handleRevokedPlugins = useCallback((revokedNames: string[]) => {
    if (revokedNames.length === 0) return;
    setUIPlugins(prev => prev.filter(p => !revokedNames.includes(p.name)));
    setNewlyAddedPlugins(prev => {
      const next = new Set(prev);
      revokedNames.forEach(name => next.delete(name));
      return next;
    });
    // Update tracking ref
    revokedNames.forEach(name => prevPluginNamesRef.current.delete(name));
  }, []);

  /**
   * Handle new plugins being added to the allowlist.
   * Marks them as newly added so the sidebar shows the "NEW" badge.
   */
  const handleAddedPlugins = useCallback((addedNames: string[]) => {
    if (addedNames.length === 0) return;
    setNewlyAddedPlugins(prev => {
      const next = new Set(prev);
      addedNames.forEach(name => next.add(name));
      return next;
    });
    // Update tracking ref
    addedNames.forEach(name => prevPluginNamesRef.current.add(name));
  }, []);

  /**
   * Clear the "NEW" badge for a specific plugin.
   * Called when the user interacts with (opens) the plugin.
   */
  const clearNewPlugin = useCallback((name: string) => {
    setNewlyAddedPlugins(prev => {
      if (!prev.has(name)) return prev;
      const next = new Set(prev);
      next.delete(name);
      return next;
    });
  }, []);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      // Add timeout to prevent indefinite loading
      const timeoutPromise = new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error('Plugin discovery timeout')), 5000)
      );
      const plugins = await Promise.race([
        pluginsApi.listUIPlugins(),
        timeoutPromise,
      ]);

      // Free-core plugins render as native workbench pages, not plugin iframes (Phase 191)
      const FREE_CORE_PLUGINS = new Set(['clarify', 'cost_tracker']);

      const uiPluginList: UIPlugin[] = plugins
        .filter(({ name }) => !FREE_CORE_PLUGINS.has(name))
        .filter(({ manifest }) => hasUI(manifest))
        .map(({ name, manifest }) => ({
          name,
          manifest,
          routes: manifest.ui?.routes || [],
          sidebarItem: manifest.ui?.sidebar_item,
        }));

      // Compute added/revoked diff (skip on first load to avoid false positives)
      const newNames = new Set(uiPluginList.map(p => p.name));
      const prevNames = prevPluginNamesRef.current;

      if (!isFirstLoadRef.current) {
        // Plugins added since last load
        const added = uiPluginList
          .map(p => p.name)
          .filter(name => !prevNames.has(name));
        // Plugins removed since last load
        const revoked = Array.from(prevNames).filter(name => !newNames.has(name));

        if (added.length > 0) handleAddedPlugins(added);
        if (revoked.length > 0) handleRevokedPlugins(revoked);
      }

      isFirstLoadRef.current = false;
      prevPluginNamesRef.current = newNames;
      setUIPlugins(uiPluginList);
    } catch (err) {
      // Silently fail - no plugins is fine
      setError(err instanceof Error ? err.message : 'Failed to discover plugins');
      setUIPlugins([]);
    } finally {
      setIsLoading(false);
    }
  }, [handleAddedPlugins, handleRevokedPlugins]);

  // Initial load
  useEffect(() => {
    refresh();
  }, [refresh]);

  // Re-fetch when backend broadcasts plugins_changed via WebSocket
  useEffect(() => {
    const handler = () => { refresh(); };
    window.addEventListener('dryade:plugins_changed', handler);
    return () => window.removeEventListener('dryade:plugins_changed', handler);
  }, [refresh]);

  // Re-fetch on WS reconnect to catch any plugins_changed missed during disconnection
  useEffect(() => {
    const handler = () => { refresh(); };
    window.addEventListener('dryade:ws_reconnected', handler);
    return () => window.removeEventListener('dryade:ws_reconnected', handler);
  }, [refresh]);

  // Compute all routes
  const allRoutes = uiPlugins.flatMap(p => p.routes);

  // Check if plugin is loaded
  const isPluginLoaded = useCallback((name: string): boolean => {
    return PluginRegistry.get(name)?.state === 'loaded';
  }, []);

  return {
    uiPlugins,
    isLoading,
    error,
    refresh,
    allRoutes,
    isPluginLoaded,
    newlyAddedPlugins,
    clearNewPlugin,
  };
}

/**
 * Hook for a single plugin's UI state
 */
export function useSinglePluginUI(pluginName: string) {
  const [state, setState] = useState<PluginState | undefined>();

  // Initialize bridge (needed for plugin communication)
  useEffect(() => {
    PluginBridge.initialize();
    return () => PluginBridge.destroy();
  }, []);

  useEffect(() => {
    const update = () => setState(PluginRegistry.get(pluginName));
    update();
    return PluginRegistry.subscribe(update);
  }, [pluginName]);

  return {
    state: state?.state || 'unloaded',
    error: state?.error,
    isLoaded: state?.state === 'loaded',
    isVerified: state?.state === 'verified' || state?.state === 'loaded',
  };
}
