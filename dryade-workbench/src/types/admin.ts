// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// Admin dashboard types matching backend API schemas

// ── RBAC Types (rights_basic plugin) ──────────────────────────

export interface AdminRole {
  id: number;
  name: string;
  description: string;
  is_builtin: boolean;
  is_custom: boolean;
  tier: string;
  priority: number;
  permission_count: number;
}

export interface RoleListResponse {
  roles: AdminRole[];
}

export interface RolePermission {
  scope: string;
  action: string;
  granted: boolean;
}

export interface RoleDetailResponse {
  role_id: number;
  role_name: string;
  permissions: RolePermission[];
  inherited_from?: string;
}

export interface AdminUser {
  user_id: string;
  email: string;
  display_name?: string;
  global_role?: string;
  is_active: boolean;
  last_seen?: string;
}

export interface UserListResponse {
  users: AdminUser[];
  total: number;
  page: number;
  per_page: number;
}

export interface UserPermissions {
  user_id: string;
  global_role?: string;
  effective_permissions: Record<string, string[]>;
  scoped_roles: Record<string, unknown>[];
  resource_overrides: Record<string, unknown>[];
}

export interface AssignRoleRequest {
  role_id: number;
  scope_type?: string;
  scope_id?: string;
}

// ── RBAC Audit Types (rights_basic plugin) ────────────────────

export interface RbacAuditEntry {
  id: number;
  actor_id: string;
  action: string;
  target_type: string;
  target_id: string;
  before_state?: Record<string, unknown>;
  after_state?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  timestamp: string;
}

export interface RbacAuditListResponse {
  entries: RbacAuditEntry[];
  total: number;
  page: number;
  per_page: number;
}

// ── Core Audit Types (audit_admin) ────────────────────────────

export interface CoreAuditEntry {
  id: number;
  user_id: string;
  action: string;
  resource_type: string;
  resource_id: string;
  ip_address: string;
  metadata?: Record<string, unknown>;
  event_severity: string;
  entry_hash: string;
  created_at: string;
}

export interface CoreAuditResponse {
  items: CoreAuditEntry[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface AuditChainStatus {
  verified: number;
  broken: number;
  first_break_id?: number;
  status: 'intact' | 'broken' | 'partial';
  message: string;
}

// ── SSO Types (zitadel_auth) ──────────────────────────────────

export interface SsoStatus {
  enabled: boolean;
  configured: boolean;
  issuer?: string;
}

export interface SsoProvider {
  id: string;
  name: string;
  enabled: boolean;
}

// ── Audit Log Shipper Types ───────────────────────────────────

export interface ShipperStatus {
  status: string;
  name: string;
  version: string;
  tier: string;
  sinks: Record<string, unknown>;
  shipping: Record<string, unknown>;
}

// ── Admin Dashboard Stats (computed client-side) ──────────────

export interface AdminStats {
  user_count: number;
  role_count: number;
  active_users: number;
  audit_event_count: number;
}

// ── LDAP Connector Types ──────────────────────────────────────

export interface LdapConfig {
  server_url: string;
  bind_dn: string;
  bind_password: string;
  base_dn: string;
  user_search_filter: string;
  user_attr_map: Record<string, string>;
  group_search_filter: string;
  group_attr_map: Record<string, string>;
  use_tls: boolean;
  connection_timeout: number;
}

export interface LdapTestResult {
  success: boolean;
  message: string;
  server_info?: Record<string, unknown>;
}

export interface LdapUser {
  dn: string;
  uid: string;
  email?: string;
  display_name?: string;
  groups: string[];
}

export interface LdapSearchResult {
  users: LdapUser[];
  total: number;
}

export interface LdapGroupMapping {
  ldap_group: string;
  local_role: string;
}

export interface LdapSyncConfig {
  group_mappings: LdapGroupMapping[];
  auto_create_users: boolean;
  auto_deactivate_missing: boolean;
}

export interface LdapSyncResult {
  created: number;
  updated: number;
  deactivated: number;
  errors: string[];
  synced_at: string;
}

export interface LdapStatus {
  configured: boolean;
  connected: boolean;
  last_sync?: string;
}

// ── SCIM Provider Types ───────────────────────────────────────

export interface ScimProviderConfig {
  patch: { supported: boolean };
  bulk: { supported: boolean };
  filter: { supported: boolean; maxResults?: number };
  changePassword: { supported: boolean };
  sort: { supported: boolean };
  etag: { supported: boolean };
}
