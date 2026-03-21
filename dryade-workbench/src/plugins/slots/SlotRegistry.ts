// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
/**
 * SlotRegistry - Singleton registry for plugin slot registrations
 *
 * Manages which plugin components are registered to which slots,
 * with priority-based ordering and change subscriptions for reactive updates.
 */

import type { ComponentType } from 'react';
import type { SlotName, SlotRegistration, SlotProps } from './types';
import { SLOT_NAMES, isValidSlotName } from './types';

class SlotRegistryClass {
  /** Map of slot names to their registered components (sorted by priority) */
  private slots = new Map<SlotName, SlotRegistration[]>();

  /** Flag to prevent duplicate loadFromBackend calls */
  private isLoading = false;

  /** Snapshot cache for useSyncExternalStore (prevents infinite loops) */
  private snapshotCache = new Map<SlotName, SlotRegistration[]>();

  constructor() {
    // Initialize with all slot names to ensure Map has entries
    this.initializeSlots();
  }

  /** Initialize all slots with empty arrays */
  private initializeSlots(): void {
    for (const name of SLOT_NAMES) {
      const emptyArray: SlotRegistration[] = [];
      this.slots.set(name, emptyArray);
      this.snapshotCache.set(name, emptyArray);
    }
  }

  /** Subscribers notified when registrations change */
  private listeners = new Set<() => void>();

  /** Cache of loaded React components by key (pluginName:componentName) */
  private componentCache = new Map<string, ComponentType<SlotProps>>();

  /**
   * Register a plugin component for a slot.
   * Components are automatically sorted by priority (lower first).
   *
   * @param slot - Target slot name
   * @param registration - Component registration details
   */
  register(slot: SlotName, registration: SlotRegistration): void {
    const existing = this.slots.get(slot) || [];

    // Prevent duplicate registrations from same plugin/component
    const isDuplicate = existing.some(
      (r) =>
        r.pluginName === registration.pluginName &&
        r.componentName === registration.componentName
    );

    if (!isDuplicate) {
      existing.push(registration);
      // Sort by priority ascending (lower = earlier in render order)
      existing.sort((a, b) => a.priority - b.priority);
      this.slots.set(slot, existing);
      // Update snapshot cache with new array reference for useSyncExternalStore
      this.snapshotCache.set(slot, [...existing]);
      this.notifyListeners();
    }
  }

  /**
   * Remove all registrations for a plugin across all slots.
   * Called when plugin is disabled or unloaded.
   *
   * @param pluginName - Name of the plugin to unregister
   */
  unregister(pluginName: string): void {
    let changed = false;

    Array.from(this.slots.entries()).forEach(([slot, registrations]) => {
      const filtered = registrations.filter((r) => r.pluginName !== pluginName);
      if (filtered.length !== registrations.length) {
        this.slots.set(slot, filtered);
        // Update snapshot cache with new array reference for useSyncExternalStore
        this.snapshotCache.set(slot, [...filtered]);
        changed = true;
      }
    });

    // Also clear component cache for this plugin
    Array.from(this.componentCache.keys()).forEach((key) => {
      if (key.startsWith(`${pluginName}:`)) {
        this.componentCache.delete(key);
      }
    });

    if (changed) {
      this.notifyListeners();
    }
  }

  /**
   * Get all registrations for a slot, sorted by priority.
   * Returns cached snapshot for useSyncExternalStore compatibility.
   *
   * @param slot - Slot name to query
   * @returns Array of registrations (empty if none) - stable reference
   */
  getSlotRegistrations(slot: SlotName): SlotRegistration[] {
    // Return from snapshot cache - this ensures stable references for useSyncExternalStore
    const cached = this.snapshotCache.get(slot);
    if (cached !== undefined) {
      return cached;
    }
    // Fallback: initialize missing slot (shouldn't happen normally)
    const emptyArray: SlotRegistration[] = [];
    this.snapshotCache.set(slot, emptyArray);
    return emptyArray;
  }

  /**
   * Get a cached component by key.
   *
   * @param key - Cache key in format "pluginName:componentName"
   * @returns Cached component or undefined
   */
  getCachedComponent(key: string): ComponentType<SlotProps> | undefined {
    return this.componentCache.get(key);
  }

  /**
   * Cache a loaded component for reuse.
   *
   * @param key - Cache key in format "pluginName:componentName"
   * @param component - React component to cache
   */
  cacheComponent(key: string, component: ComponentType<SlotProps>): void {
    this.componentCache.set(key, component);
  }

  /**
   * Subscribe to registry changes for reactive updates.
   *
   * @param listener - Callback invoked when registrations change
   * @returns Unsubscribe function
   */
  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  /**
   * Clear all registrations and cache.
   * Primarily for testing purposes.
   */
  clear(): void {
    this.slots.clear();
    this.snapshotCache.clear();
    this.componentCache.clear();
    // Re-initialize all slots with empty arrays for stable references
    this.initializeSlots();
    this.notifyListeners();
  }

  /**
   * Notify all subscribers of a change.
   */
  notifyListeners(): void {
    this.listeners.forEach((listener) => listener());
  }

  /**
   * Load slot registrations from backend API.
   * Called on app initialization to sync frontend registry with backend state.
   * Clears existing registrations first to prevent duplicates on re-authentication.
   */
  async loadFromBackend(): Promise<void> {
    // Prevent duplicate simultaneous loads
    if (this.isLoading) {
      console.debug('SlotRegistry loadFromBackend already in progress, skipping');
      return;
    }

    this.isLoading = true;
    try {
      // Import dynamically to avoid circular dependency
      const { slotsApi, pluginsApi } = await import('@/services/api');
      const { PluginRegistry } = await import('../PluginRegistry');
      const backendSlots = await slotsApi.getAll();

      // CRITICAL: Clear existing registrations first to prevent duplicates
      // This handles the case where loadFromBackend is called multiple times
      // (e.g., on re-authentication or page refresh)
      this.clear();

      // Collect unique plugin names and pending slot registrations
      const pluginNames = new Set<string>();
      const pendingRegistrations: Array<{
        slotName: SlotName;
        registration: SlotRegistration;
      }> = [];

      // Parse backend slots without registering yet (to avoid triggering re-renders)
      for (const slotName of Object.keys(backendSlots)) {
        // Validate slot name
        if (!isValidSlotName(slotName)) {
          console.warn(`Invalid slot name from backend: ${slotName}`);
          continue;
        }

        const registrations = backendSlots[slotName];
        for (const reg of registrations) {
          pluginNames.add(reg.plugin_name);
          pendingRegistrations.push({
            slotName,
            registration: {
              pluginName: reg.plugin_name,
              componentName: reg.component_name,
              priority: reg.priority,
              props: reg.props,
            },
          });
        }
      }

      // FIRST: Register plugin manifests in PluginRegistry
      // This MUST complete before slots are registered to avoid race conditions
      const verifiedPlugins = new Set<string>();
      for (const pluginName of pluginNames) {
        if (PluginRegistry.isVerified(pluginName)) {
          verifiedPlugins.add(pluginName);
          continue;
        }
        try {
          const manifest = await pluginsApi.getPluginUIManifest(pluginName);
          if (manifest) {
            PluginRegistry.register(manifest);
            verifiedPlugins.add(pluginName);
            console.debug(`Registered slot plugin manifest: ${pluginName}`);
          }
        } catch (err) {
          console.warn(`Failed to register manifest for slot plugin ${pluginName}:`, err);
        }
      }

      // THEN: Register slots only for verified plugins
      for (const { slotName, registration } of pendingRegistrations) {
        if (verifiedPlugins.has(registration.pluginName)) {
          this.register(slotName, registration);
        } else {
          console.warn(
            `Skipping slot registration for unverified plugin: ${registration.pluginName}`
          );
        }
      }

      console.debug(
        `Slot registry loaded: ${verifiedPlugins.size}/${pluginNames.size} plugins verified`
      );
    } catch (error) {
      console.warn('Failed to load slot registry from backend:', error);
      // Don't throw - slots will just be empty
    } finally {
      this.isLoading = false;
    }
  }
}

/** Singleton instance of the slot registry */
export const SlotRegistry = new SlotRegistryClass();
