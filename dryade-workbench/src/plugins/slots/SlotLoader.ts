// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
/**
 * SlotLoader - Factory for creating lazy-loaded slot components
 *
 * Handles plugin verification, bundle fetching, evaluation,
 * and component caching for slot registrations.
 */

import { lazy, type ComponentType } from 'react';
import { PluginRegistry } from '../PluginRegistry';
import { SlotRegistry } from './SlotRegistry';
import { computeSHA256Hex } from '@/ee/crypto/verifySignature.ee';
import type { SlotProps, SlotRegistration } from './types';

/** Cache for lazy component factories to prevent recreation on each render */
const lazyComponentCache = new Map<string, ComponentType<SlotProps>>();

/**
 * Get a lazy-loaded component for a slot registration.
 * Components are cached to prevent redundant loading.
 *
 * @param registration - The slot registration to load
 * @returns A lazy React component
 */
export function getSlotComponent(
  registration: SlotRegistration
): ComponentType<SlotProps> {
  const cacheKey = `${registration.pluginName}:${registration.componentName}`;

  // Return cached lazy component if exists
  const cached = lazyComponentCache.get(cacheKey);
  if (cached) return cached;

  // Create new lazy component
  const LazyComponent = lazy(async () => {
    // CRITICAL: Verify plugin before loading any code
    if (!PluginRegistry.isVerified(registration.pluginName)) {
      throw new Error(`Plugin ${registration.pluginName} not verified`);
    }

    // Check component cache in SlotRegistry (might have been loaded elsewhere)
    const cachedComponent = SlotRegistry.getCachedComponent(cacheKey);
    if (cachedComponent) {
      return { default: cachedComponent };
    }

    // Fetch and evaluate bundle
    const bundle = await fetchVerifiedBundle(registration.pluginName);
    const exports = evaluateBundle(bundle, registration.pluginName);

    const Component = exports[registration.componentName];
    if (!Component) {
      throw new Error(
        `Component ${registration.componentName} not found in ${registration.pluginName}`
      );
    }

    // Cache for future use
    SlotRegistry.cacheComponent(cacheKey, Component as ComponentType<SlotProps>);
    return { default: Component as ComponentType<SlotProps> };
  });

  lazyComponentCache.set(cacheKey, LazyComponent);
  return LazyComponent;
}

/**
 * Fetch bundle with verification.
 * Handles both plain (Tier 1/community) and encrypted (Tier 2+) bundles.
 *
 * Security model:
 * - Tier 1 (Community): Bundle travels plain, client verifies SHA-256 hash
 * - Tier 2+ (Dryade): Backend decrypts and is trusted for integrity verification
 *
 * @param pluginName - Name of the plugin
 * @returns Bundle code as string
 */
async function fetchVerifiedBundle(pluginName: string): Promise<string> {
  const plugin = PluginRegistry.get(pluginName);
  if (!plugin?.manifest.ui_bundle_hash) {
    throw new Error(`No bundle hash for plugin ${pluginName}`);
  }

  // Check if plugin is encrypted (.dryadepkg package)
  // This is determined by the backend based on actual package presence, not tier
  // Tier determines licensing requirements, encryption is a separate packaging concern
  const isEncrypted = plugin.manifest.is_encrypted === true;

  // Use appropriate endpoint
  const endpoint = isEncrypted
    ? `/api/plugins/${pluginName}/ui/bundle/decrypted`
    : `/api/plugins/${pluginName}/ui/bundle`;

  const response = await fetch(endpoint, {
    credentials: 'include',  // Send auth cookies for encrypted endpoint
  });

  if (!response.ok) {
    if (response.status === 403) {
      throw new Error(`License required for plugin ${pluginName}`);
    }
    throw new Error(`Failed to fetch bundle for ${pluginName}: ${response.status}`);
  }

  const bundleCode = await response.text();

  // Hash verification strategy per security model:
  // - Tier 1 (Community): Client verifies hash (bundle travels plain over network)
  // - Tier 2+ (Dryade): Backend is trusted for decryption, skip client hash check
  //   The backend already verified integrity during decryption
  if (!isEncrypted) {
    const hash = await computeSHA256Hex(bundleCode);
    if (hash !== plugin.manifest.ui_bundle_hash) {
      throw new Error(`Bundle hash mismatch for ${pluginName}`);
    }
  }

  return bundleCode;
}

/**
 * Safely evaluate bundle in isolated scope.
 * Bundle must be in CommonJS format or assign to module.exports.
 *
 * @param bundleCode - JavaScript code to evaluate
 * @param pluginName - Plugin name for error context
 * @returns Module exports object
 */
function evaluateBundle(
  bundleCode: string,
  pluginName: string
): Record<string, unknown> {
  // Create isolated scope for bundle execution
  const exports: Record<string, unknown> = {};
  const module = { exports };

  try {
    // Use Function constructor for marginally safer execution than eval
    // Bundle must be in CommonJS format or assign to module.exports
    const fn = new Function('module', 'exports', 'require', bundleCode);

    // Provide a minimal require stub for common dependencies
    const requireStub = (name: string): unknown => {
      // React and ReactDOM are provided by the host
      if (name === 'react' || name === 'react/jsx-runtime') {
        return (window as unknown as { React?: unknown }).React;
      }
      if (name === 'react-dom') {
        return (window as unknown as { ReactDOM?: unknown }).ReactDOM;
      }
      throw new Error(`Module ${name} not available in plugin sandbox`);
    };

    fn(module, exports, requireStub);
    return module.exports as Record<string, unknown>;
  } catch (error) {
    console.error(`Failed to evaluate bundle for ${pluginName}:`, error);
    throw error;
  }
}

/**
 * Clear the lazy component cache.
 * Useful when a plugin is unloaded and its components need to be reloaded fresh.
 *
 * @param pluginName - Optional plugin name to clear (clears all if not provided)
 */
export function clearSlotComponentCache(pluginName?: string): void {
  if (pluginName) {
    // Clear only entries for the specified plugin
    Array.from(lazyComponentCache.keys()).forEach((key) => {
      if (key.startsWith(`${pluginName}:`)) {
        lazyComponentCache.delete(key);
      }
    });
  } else {
    lazyComponentCache.clear();
  }
}
