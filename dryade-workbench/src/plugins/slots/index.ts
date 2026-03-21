// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
/**
 * Plugin UI Slot System
 *
 * Enables plugins to inject React components into predefined host page locations.
 *
 * @example
 * // In a host page (e.g., WorkflowPage.tsx)
 * import { PluginSlot } from '@/plugins/slots';
 *
 * function WorkflowPage() {
 *   return (
 *     <div>
 *       <PluginSlot name="workflow-sidebar" hostData={{ workflowId }} />
 *     </div>
 *   );
 * }
 *
 * @example
 * // Plugin registering a slot component (via PluginBridge)
 * SlotRegistry.register('workflow-sidebar', {
 *   pluginName: 'my-plugin',
 *   componentName: 'WorkflowSidebarWidget',
 *   priority: 50,
 * });
 */

// Main component for host pages
export { PluginSlot } from './PluginSlot';

// Registry singleton for slot management
export { SlotRegistry } from './SlotRegistry';

// Error boundary for slot isolation
export { SlotErrorBoundary } from './SlotErrorBoundary';

// Loader utilities
export { getSlotComponent, clearSlotComponentCache } from './SlotLoader';

// Types
export type { SlotName, SlotRegistration, SlotProps } from './types';

// Runtime constants
export { SLOT_NAMES, isValidSlotName } from './types';
