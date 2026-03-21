// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// API Client with token refresh interceptor
// This is the base client that handles authentication and request/response intercepting

const API_BASE_URL = '/api';
const TOKEN_STORAGE_KEY = 'auth_tokens';

interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

interface RequestConfig extends RequestInit {
  requiresAuth?: boolean;
}

// Get stored tokens
const getTokens = (): AuthTokens | null => {
  try {
    const stored = localStorage.getItem(TOKEN_STORAGE_KEY);
    return stored ? JSON.parse(stored) : null;
  } catch {
    return null;
  }
};

// Store tokens
const setTokens = (tokens: AuthTokens) => {
  localStorage.setItem(TOKEN_STORAGE_KEY, JSON.stringify(tokens));
};

// Clear tokens
const clearTokens = () => {
  localStorage.removeItem(TOKEN_STORAGE_KEY);
};

// Refresh the access token
const refreshAccessToken = async (): Promise<AuthTokens | null> => {
  const tokens = getTokens();
  if (!tokens?.refresh_token) return null;

  try {
    const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: tokens.refresh_token }),
    });

    if (!response.ok) {
      clearTokens();
      return null;
    }

    const newTokens = await response.json();
    setTokens(newTokens);
    return newTokens;
  } catch {
    clearTokens();
    return null;
  }
};

// Main fetch function with interceptors
export const fetchWithAuth = async <T>(
  endpoint: string,
  config: RequestConfig = {}
): Promise<T> => {
  const { requiresAuth = true, ...fetchConfig } = config;
  const url = endpoint.startsWith('http') ? endpoint : `${API_BASE_URL}${endpoint}`;

  const headers = new Headers(fetchConfig.headers);

  if (fetchConfig.body instanceof FormData) {
    // Let the browser set Content-Type with the multipart boundary
    headers.delete('Content-Type');
  } else if (!headers.has('Content-Type') && fetchConfig.body) {
    headers.set('Content-Type', 'application/json');
  }

  // Add auth header if required
  if (requiresAuth) {
    const tokens = getTokens();
    if (tokens?.access_token) {
      headers.set('Authorization', `Bearer ${tokens.access_token}`);
    }
  }

  let response = await fetch(url, {
    ...fetchConfig,
    headers,
  });

  // Handle 401 - try to refresh token
  if (response.status === 401 && requiresAuth) {
    const newTokens = await refreshAccessToken();
    if (newTokens) {
      headers.set('Authorization', `Bearer ${newTokens.access_token}`);
      response = await fetch(url, {
        ...fetchConfig,
        headers,
      });
    } else {
      // Redirect to login
      window.location.href = '/auth';
      throw new Error('Authentication required');
    }
  }

  // Handle other error statuses
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `Request failed with status ${response.status}`);
  }

  // Handle empty responses
  const contentType = response.headers.get('content-type');
  if (!contentType || !contentType.includes('application/json')) {
    const text = await response.text().catch(() => '');
    return text as unknown as T;
  }

  return response.json();
};

// Streaming fetch for SSE with timing measurements and abort support
export const fetchStream = async (
  endpoint: string,
  config: RequestConfig = {},
  onChunk: (chunk: string, timing?: { ttft?: number; interval?: number }) => void,
  signal?: AbortSignal
): Promise<void> => {
  const { requiresAuth = true, ...fetchConfig } = config;
  const url = endpoint.startsWith('http') ? endpoint : `${API_BASE_URL}${endpoint}`;

  const headers = new Headers(fetchConfig.headers);
  headers.set('Accept', 'text/event-stream');

  if (fetchConfig.body instanceof FormData) {
    headers.delete('Content-Type');
  } else if (!headers.has('Content-Type') && fetchConfig.body) {
    headers.set('Content-Type', 'application/json');
  }

  if (requiresAuth) {
    const tokens = getTokens();
    if (tokens?.access_token) {
      headers.set('Authorization', `Bearer ${tokens.access_token}`);
    }
  }

  const response = await fetch(url, {
    ...fetchConfig,
    headers,
    signal, // Pass abort signal to fetch
  });

  if (!response.ok) {
    throw new Error(`Stream request failed with status ${response.status}`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error('No response body');

  const decoder = new TextDecoder();

  // Timing measurements
  const startTime = performance.now();
  let firstTokenTime: number | null = null;
  let lastTokenTime = startTime;

  try {
    while (true) {
      // Check if aborted before reading
      if (signal?.aborted) {
        await reader.cancel();
        break;
      }

      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value, { stream: true });
      const lines = chunk.split('\n');

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6);
          if (data !== '[DONE]') {
            const now = performance.now();
            const timing: { ttft?: number; interval?: number } = {};

            // Try to determine if this is a content token for TTFT
            try {
              const parsed = JSON.parse(data);
              if (parsed.type === 'token' && firstTokenTime === null) {
                firstTokenTime = now;
                timing.ttft = firstTokenTime - startTime;
                console.log(`TTFT: ${timing.ttft.toFixed(2)}ms`);
              }
            } catch {
              // Not JSON or can't parse, skip TTFT check
            }

            // Track chunk interval
            timing.interval = now - lastTokenTime;
            if (timing.interval > 100) {
              console.log(`Slow chunk interval: ${timing.interval.toFixed(2)}ms`);
            }
            lastTokenTime = now;

            onChunk(data, timing);
          }
        }
      }
    }
  } finally {
    // Ensure reader is released on abort or completion
    try {
      await reader.cancel();
    } catch {
      // Ignore cancel errors
    }
  }
};

export { getTokens, setTokens, clearTokens };
