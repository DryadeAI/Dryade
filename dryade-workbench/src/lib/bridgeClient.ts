// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
/**
 * Fetch wrapper that transparently handles encrypted plugin bridge responses.
 *
 * Usage:
 *   const resp = await bridgeFetch("/api/ep/{token}", {
 *     headers: { Authorization: `Bearer ${jwt}` },
 *   });
 *   const data = await resp.json(); // already decrypted
 *
 * For non-encrypted responses (no X-Dryade-Encrypted: true header), passes
 * through unchanged — callers do not need to know whether a plugin uses the
 * encrypted bridge or the plaintext path.
 *
 * Session key lifecycle:
 * - Fetched once per session from GET /api/plugins/bridge/session-key
 * - Cached in module scope until JWT expires (cachedKeyExpiry)
 * - On expiry, automatically re-fetched on next bridgeFetch() call
 */

import { decryptBridgeResponse, deriveSessionKey } from "./bridgeDecrypt";

/** Base API URL — reads VITE_API_URL from build-time env, falls back to localhost. */
const API_BASE = (import.meta as unknown as { env: Record<string, string> }).env?.VITE_API_URL ?? "http://localhost:8000";

/** Module-level session key cache (survives across bridgeFetch calls). */
let cachedSessionKey: CryptoKey | null = null;
let cachedKeyExpiry: number = 0; // Unix timestamp (seconds)

/**
 * Fetch or return the cached session key for bridge decryption.
 *
 * The session key is derived client-side from:
 *   - The scoped server secret (GET /api/plugins/bridge/session-key)
 *   - The JWT sub + exp claims
 *
 * Result is cached until the JWT expires.
 *
 * @returns CryptoKey for AES-GCM decryption
 * @throws Error if the session-key endpoint is unreachable or returns an error
 */
async function getSessionKey(): Promise<CryptoKey> {
  const nowSecs = Math.floor(Date.now() / 1000);

  // Return cached key if still valid (5-second grace period before expiry)
  if (cachedSessionKey !== null && nowSecs < cachedKeyExpiry - 5) {
    return cachedSessionKey;
  }

  // Fetch session key material from server
  const token = localStorage.getItem("token") ?? "";
  const resp = await fetch(`${API_BASE}/api/plugins/bridge/session-key`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!resp.ok) {
    throw new Error(
      `Bridge session key fetch failed: HTTP ${resp.status} ${resp.statusText}`,
    );
  }

  const { secret, sub, exp } = (await resp.json()) as {
    secret: string;
    sub: string;
    exp: number;
  };

  // Decode the base64-encoded scoped server secret
  const secretBytes = Uint8Array.from(atob(secret), (c) => c.charCodeAt(0));

  // Derive the AES-GCM session key client-side (mirrors server derivation)
  cachedSessionKey = await deriveSessionKey(sub, exp, secretBytes);
  cachedKeyExpiry = exp;

  return cachedSessionKey;
}

/**
 * Clear the cached session key (e.g. after logout or JWT refresh).
 *
 * Call this whenever the user's JWT changes so that the next bridgeFetch()
 * will re-derive the session key from the new JWT claims.
 */
export function clearBridgeSessionCache(): void {
  cachedSessionKey = null;
  cachedKeyExpiry = 0;
}

/**
 * Fetch a URL, transparently decrypting encrypted plugin bridge responses.
 *
 * Behaves identically to fetch() for non-encrypted responses. For responses
 * with the `X-Dryade-Encrypted: true` header, automatically:
 * 1. Fetches (or returns cached) session key
 * 2. Reads the raw response body
 * 3. Decrypts with AES-GCM using the session key
 * 4. Returns a new Response with the decrypted body and JSON content-type
 *
 * The returned Response has the same status code as the original and has the
 * X-Dryade-Encrypted header removed so callers don't need to handle it.
 *
 * @param url - URL to fetch (absolute or relative)
 * @param init - Standard RequestInit options passed to fetch()
 * @returns Response — decrypted if encrypted, unchanged if plaintext
 * @throws Error if decryption fails (wrong key or tampered data)
 */
export async function bridgeFetch(url: string, init?: RequestInit): Promise<Response> {
  const resp = await fetch(url, init);

  // Non-encrypted response: pass through completely unchanged
  if (resp.headers.get("X-Dryade-Encrypted") !== "true") {
    return resp;
  }

  // Encrypted response: derive/retrieve session key, then decrypt
  const sessionKey = await getSessionKey();
  const encryptedBody = await resp.arrayBuffer();
  const decryptedBody = await decryptBridgeResponse(encryptedBody, sessionKey);

  // Build a new Response with the decrypted body, preserving status
  const headers = new Headers(resp.headers);
  headers.delete("X-Dryade-Encrypted"); // Remove encryption marker
  headers.set("Content-Type", "application/json"); // Decrypted payload is JSON
  headers.set("Content-Length", String(decryptedBody.byteLength));

  return new Response(decryptedBody, {
    status: resp.status,
    statusText: resp.statusText,
    headers,
  });
}
