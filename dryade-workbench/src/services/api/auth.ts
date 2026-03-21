// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// Auth & Users API - Authentication and user management

import { fetchWithAuth, getTokens, setTokens, clearTokens } from '../apiClient';
import type {
  AuthTokens,
  AuthUser,
  LoginRequest,
  RegisterRequest,
} from '@/types/api';

// Re-export token management functions for convenience
export { getTokens, setTokens, clearTokens };

// Auth API - Real backend calls
export const authApi = {
  login: async (credentials: LoginRequest): Promise<AuthTokens> => {
    const tokens = await fetchWithAuth<AuthTokens>('/auth/login', {
      method: 'POST',
      body: JSON.stringify(credentials),
      requiresAuth: false,
    });
    setTokens(tokens);
    return tokens;
  },

  register: async (data: RegisterRequest): Promise<AuthTokens> => {
    const tokens = await fetchWithAuth<AuthTokens>('/auth/register', {
      method: 'POST',
      body: JSON.stringify(data),
      requiresAuth: false,
    });
    setTokens(tokens);
    return tokens;
  },

  logout: async (): Promise<void> => {
    try {
      await fetchWithAuth<void>('/auth/logout', {
        method: 'POST',
      });
    } finally {
      clearTokens();
    }
  },

  refresh: async (refreshToken: string): Promise<AuthTokens> => {
    const tokens = await fetchWithAuth<AuthTokens>('/auth/refresh', {
      method: 'POST',
      body: JSON.stringify({ refresh_token: refreshToken }),
      requiresAuth: false,
    });
    setTokens(tokens);
    return tokens;
  },

  checkPlugins: async (): Promise<{ plugins: string[] }> => {
    try {
      const response = await fetchWithAuth<{
        plugins: Array<{ name: string }>;
        count: number;
      }>('/plugins', {
        requiresAuth: false,
      });
      const plugins = Array.isArray(response?.plugins) ? response.plugins : [];
      return { plugins: plugins.map((p) => p.name) };
    } catch {
      return { plugins: [] };
    }
  },

  setupAdmin: async (data: RegisterRequest): Promise<AuthTokens> => {
    const tokens = await fetchWithAuth<AuthTokens>('/auth/setup', {
      method: 'POST',
      body: JSON.stringify(data),
      requiresAuth: false,
    });
    setTokens(tokens);
    return tokens;
  },

  initiateSSO: async (provider: string): Promise<{ login_url: string }> => {
    // Note: SSO routes are only available when Zitadel plugin is configured
    // Routes return 404 when plugin disabled (routes not mounted)
    return fetchWithAuth<{ login_url: string }>(`/auth/sso/login/${provider}`, {
      method: 'GET',
      requiresAuth: false,
    });
  },

  requestPasswordReset: async (email: string): Promise<void> => {
    return fetchWithAuth<void>('/auth/password-reset', {
      method: 'POST',
      body: JSON.stringify({ email }),
      requiresAuth: false,
    });
  },
};


// Users API - Real backend calls
export const usersApi = {
  getCurrentUser: async (): Promise<AuthUser> => {
    return fetchWithAuth<AuthUser>('/users/me');
  },

  updateCurrentUser: async (updates: {
    display_name?: string;
    avatar_url?: string;
    preferences?: Record<string, unknown>;
  }): Promise<AuthUser> => {
    return fetchWithAuth<AuthUser>('/users/me', {
      method: 'PATCH',
      body: JSON.stringify(updates),
    });
  },

  searchUsers: async (query: string): Promise<AuthUser[]> => {
    return fetchWithAuth<AuthUser[]>(`/users/search?q=${encodeURIComponent(query)}`);
  },

  inviteUser: async (invite: {
    email: string;
    permission: 'view' | 'edit' | 'owner';
  }): Promise<{
    id: number;
    email: string;
    permission: 'view' | 'edit' | 'owner';
    status: 'pending' | 'accepted' | 'revoked';
    invited_by: string;
    created_at: string;
    updated_at: string;
  }> => {
    return fetchWithAuth<{
      id: number;
      email: string;
      permission: 'view' | 'edit' | 'owner';
      status: 'pending' | 'accepted' | 'revoked';
      invited_by: string;
      created_at: string;
      updated_at: string;
    }>('/users/invites', {
      method: 'POST',
      body: JSON.stringify(invite),
    });
  },
};
