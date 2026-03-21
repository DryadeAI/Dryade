// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import React, { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from 'react';
import { authApi, usersApi } from '@/services/api';
import { getTokens, setTokens, clearTokens } from '@/services/apiClient';
import { SlotRegistry } from '@/plugins/slots';
import type { AuthUser, LoginRequest, RegisterRequest } from '@/types/api';

interface AuthContextValue {
  user: AuthUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (credentials: LoginRequest) => Promise<void>;
  register: (data: RegisterRequest) => Promise<void>;
  logout: () => Promise<void>;
  refreshToken: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const REFRESH_INTERVAL = 25 * 60 * 1000; // 25 minutes (before 30-min expiry)

interface AuthProviderProps {
  children: ReactNode;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Token management delegated to apiClient.ts (single source of truth)

  const refreshToken = useCallback(async () => {
    const tokens = getTokens();
    if (!tokens?.refresh_token) return;

    try {
      const newTokens = await authApi.refresh(tokens.refresh_token);
      setTokens(newTokens);
    } catch (error) {
      console.error('Token refresh failed:', error);
      clearTokens();
      setUser(null);
    }
  }, []);

  const refreshUser = useCallback(async () => {
    const tokens = getTokens();
    if (!tokens) {
      setUser(null);
      return;
    }

    try {
      const currentUser = await usersApi.getCurrentUser();
      setUser(currentUser);
    } catch (error) {
      // Only clear tokens on authentication failures (401)
      const isAuthError = error instanceof Error &&
        (error.message.includes('Authentication required') ||
         error.message.includes('401') ||
         error.message.includes('Unauthorized'));

      if (isAuthError) {
        console.error('Failed to refresh user profile (auth error):', error);
        clearTokens();
        setUser(null);
      } else {
        // Network/server errors - keep current user state
        console.warn('Failed to refresh user profile (network/server error):', error);
      }
    }
  }, []);

  const login = useCallback(async (credentials: LoginRequest) => {
    setIsLoading(true);
    try {
      const tokens = await authApi.login(credentials);
      setTokens(tokens);
      const currentUser = await usersApi.getCurrentUser();
      setUser(currentUser);
    } catch (error) {
      clearTokens();
      setUser(null);
      throw error;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const register = useCallback(async (data: RegisterRequest) => {
    setIsLoading(true);
    try {
      const tokens = await authApi.register(data);
      setTokens(tokens);
      const currentUser = await usersApi.getCurrentUser();
      setUser(currentUser);
    } catch (error) {
      clearTokens();
      setUser(null);
      throw error;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      clearTokens();
      setUser(null);
    }
  }, []);

  // Initialize auth state from stored tokens
  useEffect(() => {
    let isMounted = true;

    const initAuth = async () => {
      const tokens = getTokens();
      if (!tokens) {
        if (isMounted) setIsLoading(false);
        return;
      }

      // Helper: restore minimal user from JWT when API is unreachable
      const restoreFromToken = () => {
        try {
          const tokenPayload = JSON.parse(atob(tokens.access_token.split('.')[1]));
          const now = new Date().toISOString();
          setUser({
            id: tokenPayload.sub || '',
            email: tokenPayload.email || '',
            display_name: tokenPayload.display_name,
            avatar_url: undefined,
            role: tokenPayload.role === 'admin' ? 'admin' : 'user',
            is_active: true,
            is_verified: true,
            is_external: false,
            preferences: {},
            first_seen: now,
            last_seen: now,
            created_at: now,
          });
        } catch {
          clearTokens();
          setUser(null);
        }
      };

      try {
        // Race the API call against a timeout so the app never gets stuck
        // on the loading spinner when the backend is slow or unreachable.
        const currentUser = await Promise.race([
          usersApi.getCurrentUser(),
          new Promise<never>((_, reject) =>
            setTimeout(() => reject(new Error('Auth init timeout')), 8000)
          ),
        ]);
        if (isMounted) setUser(currentUser);
      } catch (error) {
        if (!isMounted) return;
        const isAuthError = error instanceof Error &&
          (error.message.includes('Authentication required') ||
           error.message.includes('401') ||
           error.message.includes('Unauthorized'));

        if (isAuthError) {
          clearTokens();
          setUser(null);
        } else {
          // Network/server/timeout error - restore user from JWT token
          restoreFromToken();
        }
      }
      if (isMounted) setIsLoading(false);
    };

    initAuth();

    return () => { isMounted = false; };
  }, []);

  // Auto-refresh token interval
  useEffect(() => {
    const tokens = getTokens();
    if (!tokens) return;

    const interval = setInterval(refreshToken, REFRESH_INTERVAL);
    return () => clearInterval(interval);
  }, [refreshToken]);

  // Initialize plugin slot registry from backend after authentication
  // This loads slot registrations so plugins can inject UI components
  useEffect(() => {
    if (user && !isLoading) {
      SlotRegistry.loadFromBackend();
    }
  }, [user, isLoading]);

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isLoading,
        login,
        register,
        logout,
        refreshToken,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextValue => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export default AuthContext;
