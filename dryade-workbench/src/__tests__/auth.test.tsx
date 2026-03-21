// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act, cleanup } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { server } from '@/mocks/server';
import { AuthProvider, useAuth } from '@/contexts/AuthContext';
import AuthGuard from '@/components/auth/AuthGuard';

// Mock SlotRegistry to prevent backend calls during auth tests
vi.mock('@/plugins/slots', () => ({
  SlotRegistry: { loadFromBackend: vi.fn() },
}));

// Helper: renders AuthGuard with the given child, wrapping in AuthProvider + MemoryRouter
const renderWithAuth = (
  child: React.ReactNode,
  { initialPath = '/protected', isAuthenticated = false }: { initialPath?: string; isAuthenticated?: boolean } = {}
) => {
  // Set up tokens if authenticated
  if (isAuthenticated) {
    // Create a minimal JWT payload (base64 encoded)
    const payload = btoa(JSON.stringify({
      sub: 'user-1',
      email: 'test@example.com',
      display_name: 'Test User',
      role: 'user',
    }));
    localStorage.setItem('auth_tokens', JSON.stringify({
      access_token: `header.${payload}.signature`,
      refresh_token: 'test-refresh-token',
      token_type: 'Bearer',
      expires_in: 3600,
    }));
  }

  // Track current location for redirect assertions
  let currentLocation = '';
  const LocationTracker = () => {
    const location = useLocation();
    currentLocation = location.pathname;
    return <span data-testid="location">{location.pathname}</span>;
  };

  const result = render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AuthProvider>
        <Routes>
          <Route path="/protected" element={
            <AuthGuard>{child}</AuthGuard>
          } />
          <Route path="/admin" element={
            <AuthGuard requiredRole="admin">{child}</AuthGuard>
          } />
          <Route path="/auth" element={<LocationTracker />} />
          <Route path="/403" element={<LocationTracker />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>
  );

  return { ...result, getLocation: () => currentLocation };
};

// Helper: component that exposes useAuth values for testing
const AuthConsumer = ({ onAuth }: { onAuth: (auth: ReturnType<typeof useAuth>) => void }) => {
  const auth = useAuth();
  onAuth(auth);
  return (
    <div>
      <span data-testid="is-authenticated">{auth.isAuthenticated ? 'yes' : 'no'}</span>
      <span data-testid="is-loading">{auth.isLoading ? 'yes' : 'no'}</span>
      <span data-testid="user-email">{auth.user?.email || 'none'}</span>
    </div>
  );
};

describe('Auth Flow Integration Tests', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
    localStorage.clear();
  });

  describe('AuthGuard', () => {
    it('redirects unauthenticated users to /auth', async () => {
      // No tokens set = unauthenticated
      const { getLocation } = renderWithAuth(
        <div data-testid="protected-content">Protected Page</div>,
        { isAuthenticated: false }
      );

      // AuthGuard should redirect to /auth since there are no tokens
      await waitFor(() => {
        expect(getLocation()).toBe('/auth');
      });

      // Protected content should not be visible
      expect(screen.queryByTestId('protected-content')).not.toBeInTheDocument();
    });

    it('renders children when user is authenticated', async () => {
      // Mock the /users/me endpoint so AuthProvider can resolve the user
      server.use(
        http.get('/api/users/me', () => {
          return HttpResponse.json({
            id: 'user-1',
            email: 'test@example.com',
            display_name: 'Test User',
            role: 'user',
            is_active: true,
            is_verified: true,
            is_external: false,
            preferences: {},
            first_seen: new Date().toISOString(),
            last_seen: new Date().toISOString(),
            created_at: new Date().toISOString(),
          });
        })
      );

      renderWithAuth(
        <div data-testid="protected-content">Protected Page</div>,
        { isAuthenticated: true }
      );

      // Wait for auth state to load and render the protected content
      await waitFor(() => {
        expect(screen.getByTestId('protected-content')).toBeInTheDocument();
      });

      expect(screen.getByText('Protected Page')).toBeInTheDocument();
    });

    it('redirects non-admin users to /403 when requiredRole is admin', async () => {
      // Mock /users/me returning a regular user (not admin)
      server.use(
        http.get('/api/users/me', () => {
          return HttpResponse.json({
            id: 'user-1',
            email: 'test@example.com',
            display_name: 'Test User',
            role: 'user',
            is_active: true,
            is_verified: true,
            is_external: false,
            preferences: {},
            first_seen: new Date().toISOString(),
            last_seen: new Date().toISOString(),
            created_at: new Date().toISOString(),
          });
        })
      );

      const { getLocation } = renderWithAuth(
        <div data-testid="admin-content">Admin Page</div>,
        { initialPath: '/admin', isAuthenticated: true }
      );

      // Wait for auth to load, then guard should redirect to /403
      await waitFor(() => {
        expect(getLocation()).toBe('/403');
      });

      expect(screen.queryByTestId('admin-content')).not.toBeInTheDocument();
    });

    it('renders nothing while auth state is loading', () => {
      // Set tokens but do NOT mock /users/me -- AuthProvider will be in loading state
      // while the promise is pending
      server.use(
        http.get('/api/users/me', async () => {
          // Simulate slow response -- never resolves during this test
          await new Promise(() => {}); // intentionally hanging
        })
      );

      renderWithAuth(
        <div data-testid="protected-content">Protected Page</div>,
        { isAuthenticated: true }
      );

      // While loading, AuthGuard returns null -- nothing rendered
      expect(screen.queryByTestId('protected-content')).not.toBeInTheDocument();
      expect(screen.queryByTestId('location')).not.toBeInTheDocument();
    });
  });

  describe('AuthContext', () => {
    it('provides login and logout functions', async () => {
      let capturedAuth: ReturnType<typeof useAuth> | null = null;

      server.use(
        http.get('/api/users/me', () => {
          return HttpResponse.json({
            id: 'user-1',
            email: 'test@example.com',
            display_name: 'Test User',
            role: 'user',
            is_active: true,
            is_verified: true,
            is_external: false,
            preferences: {},
            first_seen: new Date().toISOString(),
            last_seen: new Date().toISOString(),
            created_at: new Date().toISOString(),
          });
        })
      );

      render(
        <MemoryRouter>
          <AuthProvider>
            <AuthConsumer onAuth={(auth) => { capturedAuth = auth; }} />
          </AuthProvider>
        </MemoryRouter>
      );

      // Wait for auth initialization to complete
      await waitFor(() => {
        expect(capturedAuth).not.toBeNull();
        expect(capturedAuth!.isLoading).toBe(false);
      });

      // Verify auth functions exist
      expect(typeof capturedAuth!.login).toBe('function');
      expect(typeof capturedAuth!.logout).toBe('function');
      expect(typeof capturedAuth!.refreshToken).toBe('function');
      expect(typeof capturedAuth!.register).toBe('function');
    });

    it('reads tokens from auth_tokens localStorage key', async () => {
      // Set tokens with specific key
      const payload = btoa(JSON.stringify({
        sub: 'user-42',
        email: 'stored@example.com',
        display_name: 'Stored User',
        role: 'user',
      }));
      localStorage.setItem('auth_tokens', JSON.stringify({
        access_token: `header.${payload}.signature`,
        refresh_token: 'stored-refresh',
        token_type: 'Bearer',
        expires_in: 3600,
      }));

      // Mock /users/me to return a user based on the stored token
      server.use(
        http.get('/api/users/me', () => {
          return HttpResponse.json({
            id: 'user-42',
            email: 'stored@example.com',
            display_name: 'Stored User',
            role: 'user',
            is_active: true,
            is_verified: true,
            is_external: false,
            preferences: {},
            first_seen: new Date().toISOString(),
            last_seen: new Date().toISOString(),
            created_at: new Date().toISOString(),
          });
        })
      );

      render(
        <MemoryRouter>
          <AuthProvider>
            <AuthConsumer onAuth={() => {}} />
          </AuthProvider>
        </MemoryRouter>
      );

      // AuthProvider reads from auth_tokens key and fetches user
      await waitFor(() => {
        expect(screen.getByTestId('user-email')).toHaveTextContent('stored@example.com');
        expect(screen.getByTestId('is-authenticated')).toHaveTextContent('yes');
      });
    });

    it('clears user state when tokens are invalid', async () => {
      // Set tokens but make /users/me return 401
      const payload = btoa(JSON.stringify({ sub: 'user-1', email: 'test@example.com' }));
      localStorage.setItem('auth_tokens', JSON.stringify({
        access_token: `header.${payload}.signature`,
        refresh_token: 'expired-refresh',
        token_type: 'Bearer',
        expires_in: 3600,
      }));

      server.use(
        http.get('/api/users/me', () => {
          return HttpResponse.json(
            { detail: 'Authentication required' },
            { status: 401 }
          );
        })
      );

      render(
        <MemoryRouter>
          <AuthProvider>
            <AuthConsumer onAuth={() => {}} />
          </AuthProvider>
        </MemoryRouter>
      );

      // Auth should clear tokens on 401 and set unauthenticated state
      await waitFor(() => {
        expect(screen.getByTestId('is-authenticated')).toHaveTextContent('no');
        expect(screen.getByTestId('user-email')).toHaveTextContent('none');
      });

      // Tokens should be cleared from localStorage
      expect(localStorage.getItem('auth_tokens')).toBeNull();
    });
  });
});
