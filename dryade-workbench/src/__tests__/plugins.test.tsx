// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { PluginRegistry } from '@/plugins/PluginRegistry';
import type { PluginManifest } from '@/plugins/types/pluginManifest';

// Helper to create a valid test manifest
const createTestManifest = (overrides: Partial<PluginManifest> = {}): PluginManifest => ({
  name: 'test-plugin',
  version: '1.0.0',
  required_tier: 'starter',
  author: 'Test Author',
  description: 'A test plugin',
  core_version_constraint: '>=0.1.0',
  plugin_dependencies: [],
  manifest_version: '1.0',
  signature: 'valid-signature-hex',
  has_ui: true,
  ui: {
    entry: '/plugins/test-plugin/bundle.js',
    routes: [{ path: '/workspace/plugins/test-plugin', title: 'Test Plugin' }],
    permissions: ['read_config'],
  },
  ui_bundle_hash: 'abc123hash',
  ...overrides,
});

describe('Plugin Loading Pipeline Tests', () => {
  // Access internal state by using the public API
  // PluginRegistry is a singleton so we need to clean it between tests
  beforeEach(() => {
    // Unregister any plugins left from previous tests
    const uiPlugins = PluginRegistry.listUIPlugins();
    for (const plugin of uiPlugins) {
      PluginRegistry.unregister(plugin.name);
    }
    // Also try to unregister common test names
    PluginRegistry.unregister('test-plugin');
    PluginRegistry.unregister('plugin-a');
    PluginRegistry.unregister('plugin-b');
    PluginRegistry.unregister('no-ui-plugin');
    PluginRegistry.unregister('invalid-plugin');
  });

  afterEach(() => {
    // Clean up
    PluginRegistry.unregister('test-plugin');
    PluginRegistry.unregister('plugin-a');
    PluginRegistry.unregister('plugin-b');
    PluginRegistry.unregister('no-ui-plugin');
    PluginRegistry.unregister('invalid-plugin');
  });

  describe('PluginRegistry basics', () => {
    it('starts with zero plugins', () => {
      const plugins = PluginRegistry.listUIPlugins();
      expect(plugins).toHaveLength(0);
    });

    it('registers a plugin with verified state', () => {
      const manifest = createTestManifest();
      PluginRegistry.register(manifest);

      const plugin = PluginRegistry.get('test-plugin');
      expect(plugin).toBeDefined();
      expect(plugin!.state).toBe('verified');
      expect(plugin!.name).toBe('test-plugin');
      expect(plugin!.manifest.version).toBe('1.0.0');
    });

    it('returns undefined for unregistered plugin', () => {
      const plugin = PluginRegistry.get('nonexistent-plugin');
      expect(plugin).toBeUndefined();
    });
  });

  describe('Plugin state transitions', () => {
    it('transitions from verified to loaded when markLoaded is called', () => {
      const manifest = createTestManifest();
      PluginRegistry.register(manifest);

      // Verify initial state
      expect(PluginRegistry.get('test-plugin')!.state).toBe('verified');

      // Mark as loaded with an iframe ref
      const mockIframe = document.createElement('iframe');
      PluginRegistry.markLoaded('test-plugin', mockIframe);

      const plugin = PluginRegistry.get('test-plugin');
      expect(plugin!.state).toBe('loaded');
      expect(plugin!.iframeRef).toBe(mockIframe);
      expect(plugin!.loadedAt).toBeDefined();
      expect(typeof plugin!.loadedAt).toBe('number');
    });

    it('transitions to error state when markError is called', () => {
      const manifest = createTestManifest();
      PluginRegistry.register(manifest);

      PluginRegistry.markError('test-plugin', 'Signature verification failed');

      const plugin = PluginRegistry.get('test-plugin');
      expect(plugin!.state).toBe('error');
      expect(plugin!.error).toBe('Signature verification failed');
    });

    it('isVerified returns true for verified and loaded states', () => {
      const manifest = createTestManifest();
      PluginRegistry.register(manifest);

      // Verified state
      expect(PluginRegistry.isVerified('test-plugin')).toBe(true);

      // Loaded state
      const mockIframe = document.createElement('iframe');
      PluginRegistry.markLoaded('test-plugin', mockIframe);
      expect(PluginRegistry.isVerified('test-plugin')).toBe(true);
    });

    it('isVerified returns false for error state', () => {
      const manifest = createTestManifest();
      PluginRegistry.register(manifest);

      PluginRegistry.markError('test-plugin', 'Failed');
      expect(PluginRegistry.isVerified('test-plugin')).toBe(false);
    });

    it('isVerified returns false for unknown plugin', () => {
      expect(PluginRegistry.isVerified('unknown')).toBe(false);
    });
  });

  describe('Plugin listing and filtering', () => {
    it('lists only plugins with UI manifests', () => {
      // Register plugin with UI
      PluginRegistry.register(createTestManifest({ name: 'plugin-a' }));

      // Register plugin without UI
      PluginRegistry.register(createTestManifest({
        name: 'no-ui-plugin',
        has_ui: false,
        ui: undefined,
        ui_bundle_hash: undefined,
      }));

      const uiPlugins = PluginRegistry.listUIPlugins();
      expect(uiPlugins).toHaveLength(1);
      expect(uiPlugins[0].name).toBe('plugin-a');
    });

    it('unregisters a plugin and removes it from listings', () => {
      PluginRegistry.register(createTestManifest({ name: 'plugin-a' }));
      PluginRegistry.register(createTestManifest({ name: 'plugin-b' }));

      expect(PluginRegistry.listUIPlugins()).toHaveLength(2);

      PluginRegistry.unregister('plugin-a');

      expect(PluginRegistry.listUIPlugins()).toHaveLength(1);
      expect(PluginRegistry.get('plugin-a')).toBeUndefined();
      expect(PluginRegistry.get('plugin-b')).toBeDefined();
    });
  });

  describe('Subscription and notifications', () => {
    it('notifies subscribers when plugins are registered', () => {
      const listener = vi.fn();
      const unsubscribe = PluginRegistry.subscribe(listener);

      PluginRegistry.register(createTestManifest());
      expect(listener).toHaveBeenCalledTimes(1);

      unsubscribe();
    });

    it('notifies subscribers when plugin state changes', () => {
      PluginRegistry.register(createTestManifest());

      const listener = vi.fn();
      const unsubscribe = PluginRegistry.subscribe(listener);

      // markLoaded triggers notification
      const mockIframe = document.createElement('iframe');
      PluginRegistry.markLoaded('test-plugin', mockIframe);
      expect(listener).toHaveBeenCalledTimes(1);

      // markError triggers notification
      PluginRegistry.markError('test-plugin', 'Error');
      expect(listener).toHaveBeenCalledTimes(2);

      unsubscribe();
    });

    it('stops notifying after unsubscribe', () => {
      const listener = vi.fn();
      const unsubscribe = PluginRegistry.subscribe(listener);

      PluginRegistry.register(createTestManifest());
      expect(listener).toHaveBeenCalledTimes(1);

      unsubscribe();

      // Further changes should not trigger the listener
      PluginRegistry.unregister('test-plugin');
      expect(listener).toHaveBeenCalledTimes(1); // still 1
    });
  });

  describe('Iframe reference management', () => {
    it('returns iframe reference for loaded plugin', () => {
      PluginRegistry.register(createTestManifest());
      const mockIframe = document.createElement('iframe');
      PluginRegistry.markLoaded('test-plugin', mockIframe);

      const iframe = PluginRegistry.getIframe('test-plugin');
      expect(iframe).toBe(mockIframe);
    });

    it('returns undefined iframe for non-loaded plugin', () => {
      PluginRegistry.register(createTestManifest());
      // Plugin is verified but not loaded -- no iframe yet
      const iframe = PluginRegistry.getIframe('test-plugin');
      expect(iframe).toBeUndefined();
    });

    it('returns undefined iframe for unknown plugin', () => {
      const iframe = PluginRegistry.getIframe('nonexistent');
      expect(iframe).toBeUndefined();
    });
  });
});
