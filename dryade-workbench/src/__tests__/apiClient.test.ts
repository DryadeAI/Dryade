// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { describe, it, expect, beforeEach } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import { fetchWithAuth, clearTokens } from '../services/apiClient';

describe('API Client', () => {
  beforeEach(() => {
    // Clear tokens before each test
    clearTokens();
  });

  describe('fetchWithAuth', () => {
    it('should successfully fetch data from health endpoint', async () => {
      // Mock the health endpoint
      server.use(
        http.get('/api/health', () => {
          return HttpResponse.json({
            status: 'ok',
            timestamp: '2026-01-27T10:00:00Z',
          });
        })
      );

      // Make request using apiClient
      const response = await fetchWithAuth<{ status: string; timestamp: string }>(
        '/health',
        { requiresAuth: false }
      );

      // Assert response matches mock
      expect(response).toEqual({
        status: 'ok',
        timestamp: '2026-01-27T10:00:00Z',
      });
    });

    it('should make requests without auth when requiresAuth is false', async () => {
      server.use(
        http.get('/api/public', ({ request }) => {
          const authHeader = request.headers.get('Authorization');

          // Should not have Authorization header
          if (authHeader) {
            return new HttpResponse(null, { status: 400 });
          }

          return HttpResponse.json({ message: 'public data' });
        })
      );

      const response = await fetchWithAuth<{ message: string }>(
        '/public',
        { requiresAuth: false }
      );

      expect(response).toEqual({ message: 'public data' });
    });

    it('should handle error responses correctly', async () => {
      server.use(
        http.get('/api/error', () => {
          return HttpResponse.json(
            { detail: 'Not found' },
            { status: 404 }
          );
        })
      );

      await expect(
        fetchWithAuth('/error', { requiresAuth: false })
      ).rejects.toThrow('Not found');
    });

    it('should include auth header when requiresAuth is true and tokens exist', async () => {
      // Store tokens in localStorage
      localStorage.setItem('auth_tokens', JSON.stringify({
        access_token: 'test-token',
        refresh_token: 'refresh-token',
        token_type: 'Bearer',
        expires_in: 3600,
      }));

      server.use(
        http.get('/api/protected', ({ request }) => {
          const authHeader = request.headers.get('Authorization');

          if (authHeader === 'Bearer test-token') {
            return HttpResponse.json({ message: 'authorized' });
          }

          return new HttpResponse(null, { status: 401 });
        })
      );

      const response = await fetchWithAuth<{ message: string }>(
        '/protected',
        { requiresAuth: true }
      );

      expect(response).toEqual({ message: 'authorized' });
    });
  });
});
