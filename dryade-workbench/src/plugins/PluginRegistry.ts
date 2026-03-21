// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import type { PluginManifest, PluginUIManifest } from './types/pluginManifest';

export type PluginLoadState = 'unloaded' | 'verifying' | 'verified' | 'loading' | 'loaded' | 'error';

export interface PluginState {
  name: string;
  manifest: PluginManifest;
  uiManifest: PluginUIManifest | null;
  state: PluginLoadState;
  error?: string;
  iframeRef?: HTMLIFrameElement;
  loadedAt?: number;
}

class PluginRegistryClass {
  private plugins = new Map<string, PluginState>();
  private listeners = new Set<() => void>();

  /**
   * Register a plugin after manifest verification
   */
  register(manifest: PluginManifest): void {
    this.plugins.set(manifest.name, {
      name: manifest.name,
      manifest,
      uiManifest: manifest.ui || null,
      state: 'verified',
    });
    this.notifyListeners();
  }

  /**
   * Mark plugin as loaded and store iframe reference
   */
  markLoaded(name: string, iframeRef: HTMLIFrameElement): void {
    const plugin = this.plugins.get(name);
    if (plugin) {
      plugin.state = 'loaded';
      plugin.iframeRef = iframeRef;
      plugin.loadedAt = Date.now();
      this.notifyListeners();
    }
  }

  /**
   * Mark plugin as errored
   */
  markError(name: string, error: string): void {
    const plugin = this.plugins.get(name);
    if (plugin) {
      plugin.state = 'error';
      plugin.error = error;
      this.notifyListeners();
    }
  }

  /**
   * Check if plugin is verified and ready for communication
   */
  isVerified(name: string): boolean {
    const plugin = this.plugins.get(name);
    return plugin?.state === 'verified' || plugin?.state === 'loaded';
  }

  /**
   * Get iframe reference for plugin (for postMessage targeting)
   */
  getIframe(name: string): HTMLIFrameElement | undefined {
    return this.plugins.get(name)?.iframeRef;
  }

  /**
   * Get plugin state
   */
  get(name: string): PluginState | undefined {
    return this.plugins.get(name);
  }

  /**
   * List all plugins with UI
   */
  listUIPlugins(): PluginState[] {
    return Array.from(this.plugins.values()).filter(p => p.uiManifest !== null);
  }

  /**
   * Unregister plugin (on unload or error)
   */
  unregister(name: string): void {
    this.plugins.delete(name);
    this.notifyListeners();
  }

  /**
   * Subscribe to registry changes
   */
  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private notifyListeners(): void {
    this.listeners.forEach(l => l());
  }
}

// Singleton export
export const PluginRegistry = new PluginRegistryClass();
