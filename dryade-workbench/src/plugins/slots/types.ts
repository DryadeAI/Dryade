// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
/**
 * Slot types for the plugin UI slot system
 *
 * Enables plugins to inject React components into predefined host page locations.
 */

/**
 * Predefined slot names - plugins can only register components for these locations.
 * This is a fixed set to ensure type safety and prevent arbitrary slot injection.
 */
export type SlotName =
  | 'workflow-sidebar'    // Planner tab area in WorkflowPage
  | 'workflow-toolbar'    // Toolbar buttons in WorkflowPage header
  | 'dashboard-widget'    // Widget cards on Dashboard
  | 'chat-panel'          // Right panel in ChatPage
  | 'settings-section'    // Additional settings in SettingsPage
  | 'agent-detail-panel'  // Panel on Agent detail page
  | 'nav-footer'          // Bottom of sidebar navigation
  | 'modal-extension';    // Extend modals (completion, input, etc.)

/**
 * Runtime array of slot names for validation
 */
export const SLOT_NAMES: readonly SlotName[] = [
  'workflow-sidebar',
  'workflow-toolbar',
  'dashboard-widget',
  'chat-panel',
  'settings-section',
  'agent-detail-panel',
  'nav-footer',
  'modal-extension',
] as const;

/**
 * Validates a string as a valid SlotName
 */
export function isValidSlotName(name: string): name is SlotName {
  return SLOT_NAMES.includes(name as SlotName);
}

/**
 * Registration for a plugin component in a slot
 */
export interface SlotRegistration {
  /** Plugin name (must match manifest name) */
  pluginName: string;
  /** Export name from plugin UI bundle */
  componentName: string;
  /** Render order - lower numbers render first (default: 100) */
  priority: number;
  /** Optional additional props to pass to the component */
  props?: Record<string, unknown>;
}

/**
 * Props passed to slot components when rendered
 */
export interface SlotProps {
  /** The plugin name this component belongs to */
  pluginName: string;
  /** The slot this component is rendered in */
  slotName: SlotName;
  /** Optional data from the host page */
  hostData?: Record<string, unknown>;
}
