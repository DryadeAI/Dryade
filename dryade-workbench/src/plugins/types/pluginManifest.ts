// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// Plugin UI permission types (matches backend PluginUIPermission)
export type PluginUIPermission = 'read_config' | 'write_config' | 'api_access' | 'api_proxy' | 'audio_capture';

// Plugin UI route configuration
export interface PluginUIRoute {
  path: string;        // e.g., "/workspace/plugins/semantic_cache" or "/trainer"
  title?: string;      // Display title (optional)
  component?: string;  // Component name for internal routing
  icon?: string;       // Lucide icon name
}

// Plugin UI sidebar item configuration
export interface PluginUISidebarItem {
  label: string;
  icon?: string;
  parent?: string;     // Default: "plugins"
}

// Plugin UI manifest (nested under "ui" in main manifest)
export interface PluginUIManifest {
  entry: string;                    // Path to JS bundle
  styles?: string;                  // Optional CSS
  routes: PluginUIRoute[];
  sidebar_item?: PluginUISidebarItem;
  permissions: PluginUIPermission[];
  max_bundle_size_kb?: number;      // Default 500

  /**
   * Slot components this plugin registers.
   * Optional - mainly for documentation since registration happens at runtime.
   * Format: { "slot-name": "ComponentExportName" }
   *
   * @example
   * slot_components: {
   *   "workflow-sidebar": "WorkflowSidebarWidget",
   *   "dashboard-widget": "DashboardMetricsCard"
   * }
   */
  slot_components?: Record<string, string>;
}

// Full plugin manifest with UI fields
export interface PluginManifest {
  name: string;
  version: string;
  required_tier: 'starter' | 'team' | 'enterprise';
  author: string;
  description: string;
  core_version_constraint: string;
  plugin_dependencies: string[];
  manifest_version: string;
  icon?: string;  // Lucide icon name (PascalCase)
  signature: string;
  signature_pq?: string;  // Dilithium3 post-quantum signature (optional, for hybrid security)

  // UI fields (optional)
  has_ui?: boolean;
  ui?: PluginUIManifest;
  ui_bundle_hash?: string;  // SHA-256 hash of UI bundle

  // Encryption status (added by backend at runtime)
  // True if plugin is packaged as .dryadepkg (encrypted bundle)
  // False for regular source-based plugins
  is_encrypted?: boolean;
}

// Type guard for UI-enabled plugins
export function hasUI(manifest: PluginManifest): manifest is PluginManifest & { has_ui: true; ui: PluginUIManifest; ui_bundle_hash: string } {
  return manifest.has_ui === true && !!manifest.ui && !!manifest.ui_bundle_hash;
}
