// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// Admin API service — calls existing backend endpoints for admin dashboard

import { fetchWithAuth } from '../apiClient';
import type {
  RoleListResponse,
  RoleDetailResponse,
  UserListResponse,
  UserPermissions,
  AssignRoleRequest,
  RbacAuditListResponse,
  CoreAuditResponse,
  AuditChainStatus,
  SsoStatus,
  SsoProvider,
  ShipperStatus,
  LdapConfig,
  LdapTestResult,
  LdapSearchResult,
  LdapSyncConfig,
  LdapSyncResult,
  LdapStatus,
  ScimProviderConfig,
} from '@/types/admin';

// ── RBAC (rights_basic plugin) ────────────────────────────────

const RBAC_PREFIX = '/plugins/rights_basic';

export const adminApi = {
  /** List all roles */
  listRoles: (includeCustom?: boolean): Promise<RoleListResponse> =>
    fetchWithAuth<RoleListResponse>(
      `${RBAC_PREFIX}/roles${includeCustom ? '?include_custom=true' : ''}`
    ),

  /** Get permission matrix for a role */
  getRolePermissions: (roleId: number): Promise<RoleDetailResponse> =>
    fetchWithAuth<RoleDetailResponse>(`${RBAC_PREFIX}/roles/${roleId}/permissions`),

  /** List users with optional filters */
  listUsers: (params?: {
    role?: string;
    page?: number;
    per_page?: number;
  }): Promise<UserListResponse> => {
    const search = new URLSearchParams();
    if (params?.role) search.set('role', params.role);
    if (params?.page) search.set('page', String(params.page));
    if (params?.per_page) search.set('per_page', String(params.per_page));
    const qs = search.toString();
    return fetchWithAuth<UserListResponse>(
      `${RBAC_PREFIX}/users${qs ? `?${qs}` : ''}`
    );
  },

  /** Get effective permissions for a user */
  getUserPermissions: (userId: string): Promise<UserPermissions> =>
    fetchWithAuth<UserPermissions>(`${RBAC_PREFIX}/users/${userId}/permissions`),

  /** Assign a role to a user */
  assignRole: (userId: string, body: AssignRoleRequest): Promise<void> =>
    fetchWithAuth<void>(`${RBAC_PREFIX}/users/${userId}/roles`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  /** Remove a role from a user */
  removeRole: (
    userId: string,
    roleId: number,
    scopeType?: string,
    scopeId?: string
  ): Promise<void> => {
    const search = new URLSearchParams();
    if (scopeType) search.set('scope_type', scopeType);
    if (scopeId) search.set('scope_id', scopeId);
    const qs = search.toString();
    return fetchWithAuth<void>(
      `${RBAC_PREFIX}/users/${userId}/roles/${roleId}${qs ? `?${qs}` : ''}`,
      { method: 'DELETE' }
    );
  },

  // ── RBAC Audit ──────────────────────────────────────────────

  /** List RBAC audit entries */
  listRbacAudit: (params?: {
    actor_id?: string;
    action?: string;
    target_type?: string;
    page?: number;
    per_page?: number;
  }): Promise<RbacAuditListResponse> => {
    const search = new URLSearchParams();
    if (params?.actor_id) search.set('actor_id', params.actor_id);
    if (params?.action) search.set('action', params.action);
    if (params?.target_type) search.set('target_type', params.target_type);
    if (params?.page) search.set('page', String(params.page));
    if (params?.per_page) search.set('per_page', String(params.per_page));
    const qs = search.toString();
    return fetchWithAuth<RbacAuditListResponse>(
      `${RBAC_PREFIX}/audit${qs ? `?${qs}` : ''}`
    );
  },

  // ── Core Audit (audit_admin) ────────────────────────────────

  /** Query core audit log entries */
  queryCoreAudit: (params?: {
    user_id?: string;
    action?: string;
    resource_type?: string;
    severity?: string;
    date_from?: string;
    date_to?: string;
    page?: number;
    per_page?: number;
  }): Promise<CoreAuditResponse> => {
    const search = new URLSearchParams();
    if (params?.user_id) search.set('user_id', params.user_id);
    if (params?.action) search.set('action', params.action);
    if (params?.resource_type) search.set('resource_type', params.resource_type);
    if (params?.severity) search.set('severity', params.severity);
    if (params?.date_from) search.set('date_from', params.date_from);
    if (params?.date_to) search.set('date_to', params.date_to);
    if (params?.page) search.set('page', String(params.page));
    if (params?.per_page) search.set('per_page', String(params.per_page));
    const qs = search.toString();
    return fetchWithAuth<CoreAuditResponse>(
      `/admin/audit${qs ? `?${qs}` : ''}`
    );
  },

  /** Export audit logs as JSON blob */
  exportAuditLogs: async (params?: {
    date_from?: string;
    date_to?: string;
  }): Promise<Blob> => {
    const search = new URLSearchParams();
    if (params?.date_from) search.set('date_from', params.date_from);
    if (params?.date_to) search.set('date_to', params.date_to);
    const qs = search.toString();
    // Use raw fetch for blob response
    const response = await fetchWithAuth<Response>(
      `/admin/audit/export${qs ? `?${qs}` : ''}`,
      { headers: { Accept: 'application/json' } }
    );
    // fetchWithAuth returns parsed JSON by default, but for blob we need the raw response
    // Workaround: return the response as-is when it's already a blob
    if (response instanceof Blob) return response;
    // If it came back as parsed JSON, convert to blob
    return new Blob([JSON.stringify(response)], { type: 'application/json' });
  },

  /** Verify audit hash chain integrity */
  verifyAuditChain: (limit?: number, offset?: number): Promise<AuditChainStatus> => {
    const search = new URLSearchParams();
    if (limit) search.set('limit', String(limit));
    if (offset) search.set('offset', String(offset));
    const qs = search.toString();
    return fetchWithAuth<AuditChainStatus>(
      `/admin/audit/verify-chain${qs ? `?${qs}` : ''}`
    );
  },

  // ── SSO (zitadel_auth) ──────────────────────────────────────

  /** Get SSO configuration status */
  getSsoStatus: (): Promise<SsoStatus> =>
    fetchWithAuth<SsoStatus>('/auth/sso/status', { requiresAuth: true }),

  /** Get list of SSO providers */
  getSsoProviders: (): Promise<{ providers: SsoProvider[]; issuer: string }> =>
    fetchWithAuth<{ providers: SsoProvider[]; issuer: string }>('/auth/sso/providers'),

  // ── Audit Log Shipper ───────────────────────────────────────

  /** Get audit log shipper status */
  getShipperStatus: (): Promise<ShipperStatus> =>
    fetchWithAuth<ShipperStatus>('/audit-log-shipper/status'),

  // ── LDAP Connector ──────────────────────────────────────────

  /** Get LDAP configuration (password masked) */
  ldapGetConfig: (): Promise<LdapConfig> =>
    fetchWithAuth<LdapConfig>('/plugins/ldap_connector/config'),

  /** Update LDAP configuration */
  ldapUpdateConfig: (config: LdapConfig): Promise<LdapConfig> =>
    fetchWithAuth<LdapConfig>('/plugins/ldap_connector/config', {
      method: 'PUT',
      body: JSON.stringify(config),
    }),

  /** Test LDAP connectivity */
  ldapTestConnection: (): Promise<LdapTestResult> =>
    fetchWithAuth<LdapTestResult>('/plugins/ldap_connector/test', { method: 'POST' }),

  /** Search LDAP users */
  ldapSearchUsers: (filter?: string, limit?: number): Promise<LdapSearchResult> => {
    const search = new URLSearchParams();
    if (filter) search.set('filter', filter);
    if (limit) search.set('limit', String(limit));
    const qs = search.toString();
    return fetchWithAuth<LdapSearchResult>(
      `/plugins/ldap_connector/users${qs ? `?${qs}` : ''}`
    );
  },

  /** Run LDAP user/group synchronization */
  ldapSync: (config: LdapSyncConfig): Promise<LdapSyncResult> =>
    fetchWithAuth<LdapSyncResult>('/plugins/ldap_connector/sync', {
      method: 'POST',
      body: JSON.stringify(config),
    }),

  /** Get LDAP connector status */
  ldapGetStatus: (): Promise<LdapStatus> =>
    fetchWithAuth<LdapStatus>('/plugins/ldap_connector/status'),

  // ── SCIM Provider ───────────────────────────────────────────

  /** Get SCIM service provider configuration */
  scimGetServiceProviderConfig: (): Promise<ScimProviderConfig> =>
    fetchWithAuth<ScimProviderConfig>('/scim/v2/ServiceProviderConfig', { requiresAuth: false }),
};
