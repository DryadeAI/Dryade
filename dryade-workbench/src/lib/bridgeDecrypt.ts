// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
/**
 * Client-side session key derivation and AES-GCM decryption
 * for the encrypted plugin bridge.
 *
 * The server derives the same session key from the JWT claims
 * and a scoped server secret. The client receives the scoped
 * secret via a one-time key exchange at auth time
 * (GET /api/plugins/bridge/session-key).
 *
 * Key derivation mirrors server-side EncryptedPluginBridge._extract_session_key():
 *   HMAC-SHA256(scoped_secret, "{sub}:{exp}")
 *
 * Response format from server: [12-byte nonce][ciphertext + 16-byte GCM tag]
 */

/**
 * Derive a session CryptoKey from JWT claims and the scoped server secret.
 *
 * Replicates the server-side derivation:
 *   HMAC-SHA256(scopedServerSecret, "{jwtSub}:{jwtExp}")
 *
 * @param jwtSub - JWT subject claim (user ID string)
 * @param jwtExp - JWT expiry claim (Unix timestamp integer)
 * @param serverSecret - Raw bytes of the scoped server secret (from session-key endpoint)
 * @returns CryptoKey suitable for AES-GCM decryption
 */
export async function deriveSessionKey(
  jwtSub: string,
  jwtExp: number,
  serverSecret: Uint8Array,
): Promise<CryptoKey> {
  const encoder = new TextEncoder();
  const data = encoder.encode(`${jwtSub}:${jwtExp}`);

  // Import the scoped server secret as an HMAC-SHA256 key
  const hmacKey = await crypto.subtle.importKey(
    "raw",
    serverSecret,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );

  // HMAC-SHA256(scopedServerSecret, "{sub}:{exp}") → 32-byte session key material
  const signature = await crypto.subtle.sign("HMAC", hmacKey, data);

  // Import the 32-byte HMAC output as an AES-GCM decryption key
  return crypto.subtle.importKey(
    "raw",
    signature,
    { name: "AES-GCM" },
    false,
    ["decrypt"],
  );
}

/**
 * Decrypt a bridge-encrypted response body using AES-256-GCM.
 *
 * Expected layout from server:
 *   [12-byte random nonce][ciphertext + 16-byte GCM authentication tag]
 *
 * @param encryptedBytes - Raw response body bytes from an X-Dryade-Encrypted response
 * @param sessionKey - CryptoKey derived via deriveSessionKey()
 * @returns Decrypted plaintext bytes (typically JSON)
 * @throws DOMException if the key is wrong or data is corrupted (GCM tag mismatch)
 */
export async function decryptBridgeResponse(
  encryptedBytes: ArrayBuffer,
  sessionKey: CryptoKey,
): Promise<ArrayBuffer> {
  if (encryptedBytes.byteLength < 12) {
    throw new Error(
      `Bridge response too short: ${encryptedBytes.byteLength} bytes (expected nonce + ciphertext)`,
    );
  }

  // Split: first 12 bytes = nonce, rest = ciphertext + 16-byte GCM tag
  const nonce = encryptedBytes.slice(0, 12);
  const ciphertext = encryptedBytes.slice(12);

  return crypto.subtle.decrypt({ name: "AES-GCM", iv: nonce }, sessionKey, ciphertext);
}
