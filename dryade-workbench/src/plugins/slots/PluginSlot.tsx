// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
/**
 * PluginSlot - Host component for rendering plugin slot contents
 *
 * Renders registered plugin components for a named slot location.
 * Empty slots render nothing (no DOM elements).
 */

import { Suspense, useSyncExternalStore, memo } from 'react';
import { SlotRegistry } from './SlotRegistry';
import { SlotErrorBoundary } from './SlotErrorBoundary';
import { getSlotComponent } from './SlotLoader';
import type { SlotName, SlotProps, SlotRegistration } from './types';

interface PluginSlotProps {
  /** The slot name to render */
  name: SlotName;
  /** Optional data from the host page to pass to slot components */
  hostData?: Record<string, unknown>;
  /** Optional custom loading fallback */
  fallback?: React.ReactNode;
  /** Optional className for the slot wrapper */
  className?: string;
}

/**
 * Hook to subscribe to slot registry changes.
 * Uses useSyncExternalStore for concurrent-safe subscriptions.
 */
function useSlotRegistry(slotName: SlotName): SlotRegistration[] {
  return useSyncExternalStore(
    (callback) => SlotRegistry.subscribe(callback),
    () => SlotRegistry.getSlotRegistrations(slotName),
    () => SlotRegistry.getSlotRegistrations(slotName) // Server snapshot (same as client)
  );
}

/**
 * Loading skeleton shown while slot components are loading
 */
function SlotSkeleton() {
  return (
    <div className="animate-pulse bg-muted rounded h-8 w-full" />
  );
}

/**
 * Individual slot item renderer (memoized for performance)
 */
const SlotItem = memo(function SlotItem({
  registration,
  slotName,
  hostData,
  fallback,
}: {
  registration: SlotRegistration;
  slotName: SlotName;
  hostData?: Record<string, unknown>;
  fallback?: React.ReactNode;
}) {
  const SlotComponent = getSlotComponent(registration);
  const slotProps: SlotProps = {
    pluginName: registration.pluginName,
    slotName,
    hostData,
    ...registration.props,
  };

  return (
    <SlotErrorBoundary
      key={`${registration.pluginName}-${registration.componentName}`}
      pluginName={registration.pluginName}
    >
      <Suspense fallback={fallback || <SlotSkeleton />}>
        <SlotComponent {...slotProps} />
      </Suspense>
    </SlotErrorBoundary>
  );
});

/**
 * PluginSlot renders all registered components for a named slot.
 *
 * Key behaviors:
 * - Empty slots render nothing (no wrapper div, no space taken)
 * - Components are rendered in priority order (lower priority first)
 * - Each component is wrapped in error boundary and suspense
 * - Updates reactively when registrations change
 *
 * @example
 * // In WorkflowPage.tsx
 * <PluginSlot name="workflow-sidebar" hostData={{ workflowId }} />
 */
export function PluginSlot({
  name,
  hostData,
  fallback,
  className,
}: PluginSlotProps) {
  const registrations = useSlotRegistry(name);

  // Empty slot = render nothing (no wrapper div, no space)
  if (registrations.length === 0) {
    return null;
  }

  return (
    <div className={className} data-slot={name}>
      {registrations.map((reg) => (
        <SlotItem
          key={`${reg.pluginName}-${reg.componentName}`}
          registration={reg}
          slotName={name}
          hostData={hostData}
          fallback={fallback}
        />
      ))}
    </div>
  );
}
