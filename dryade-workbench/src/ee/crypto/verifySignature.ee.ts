// Licensed under the Dryade Enterprise Edition License. See LICENSE_EE.md.
// Licensed under LICENSE_EE.md -- see repository root

import * as ed25519Noble from '@noble/ed25519';
import { sha512, sha256 } from '@noble/hashes/sha2.js';
import type { PluginManifest } from '../../plugins/types/pluginManifest';

// Configure @noble/ed25519 to use pure JS sha512 from @noble/hashes
// This is required when crypto.subtle is not available (e.g., non-HTTPS contexts)
// Set sync sha512 - used by verify(), sign(), getPublicKey()
ed25519Noble.hashes.sha512 = (message: Uint8Array) => sha512(message);
// Set async sha512 - used by verifyAsync(), signAsync(), getPublicKeyAsync()
ed25519Noble.hashes.sha512Async = async (message: Uint8Array) => sha512(message);

import { verifyMlDsa65Signature } from './verifyMlDsa.ee';

// Dryade public keys - embedded at build time via env vars
// Ed25519: hex-encoded 32-byte public key
const DRYADE_PUBLIC_KEY_HEX = import.meta.env.VITE_DRYADE_PUBLIC_KEY || '';
// ML-DSA-65: hex-encoded 1952-byte public key (PQ signature verification)
const DRYADE_PUBLIC_KEY_PQ_HEX = import.meta.env.VITE_DRYADE_PUBLIC_KEY_PQ || '';

/**
 * Convert hex string to Uint8Array
 */
function hexToBytes(hex: string): Uint8Array {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < bytes.length; i++) {
    bytes[i] = parseInt(hex.substring(i * 2, i * 2 + 2), 16);
  }
  return bytes;
}

/**
 * Check if WebCrypto supports Ed25519
 */
async function supportsWebCryptoEd25519(): Promise<boolean> {
  try {
    // Try importing a test key - this will fail if Ed25519 not supported
    const testKey = new Uint8Array(32).fill(0);
    testKey[0] = 1; // Valid point on curve
    await crypto.subtle.importKey(
      'raw',
      testKey,
      { name: 'Ed25519' },
      false,
      ['verify']
    );
    return true;
  } catch {
    return false;
  }
}

/**
 * Verify Ed25519 signature using WebCrypto API
 */
async function verifyWithWebCrypto(
  signatureBytes: Uint8Array,
  messageBytes: Uint8Array,
  publicKeyBytes: Uint8Array
): Promise<boolean> {
  const cryptoKey = await crypto.subtle.importKey(
    'raw',
    publicKeyBytes.buffer.slice(publicKeyBytes.byteOffset, publicKeyBytes.byteOffset + publicKeyBytes.byteLength) as ArrayBuffer,
    { name: 'Ed25519' },
    false,
    ['verify']
  );

  return crypto.subtle.verify(
    { name: 'Ed25519' },
    cryptoKey,
    signatureBytes.buffer.slice(signatureBytes.byteOffset, signatureBytes.byteOffset + signatureBytes.byteLength) as ArrayBuffer,
    messageBytes.buffer.slice(messageBytes.byteOffset, messageBytes.byteOffset + messageBytes.byteLength) as ArrayBuffer
  );
}

/**
 * Verify Ed25519 signature using @noble/ed25519 (fallback)
 * Uses verifyAsync which doesn't require hashes.sha512 to be set
 */
async function verifyWithNoble(
  signatureBytes: Uint8Array,
  messageBytes: Uint8Array,
  publicKeyBytes: Uint8Array
): Promise<boolean> {
  return ed25519Noble.verifyAsync(signatureBytes, messageBytes, publicKeyBytes);
}

/**
 * Verify Ed25519 signature with automatic WebCrypto/noble selection
 *
 * @param signatureHex - Hex-encoded 64-byte signature
 * @param messageBytes - Message that was signed
 * @param publicKeyHex - Hex-encoded 32-byte public key (defaults to DRYADE_PUBLIC_KEY_HEX)
 * @returns true if signature is valid
 */
export async function verifyEd25519Signature(
  signatureHex: string,
  messageBytes: Uint8Array,
  publicKeyHex: string = DRYADE_PUBLIC_KEY_HEX
): Promise<boolean> {
  if (!publicKeyHex) {
    console.warn('No public key configured for signature verification');
    return false;
  }

  try {
    const signatureBytes = hexToBytes(signatureHex);
    const publicKeyBytes = hexToBytes(publicKeyHex);

    // Validate lengths
    if (signatureBytes.length !== 64) {
      console.error(`Invalid signature length: ${signatureBytes.length} (expected 64)`);
      return false;
    }
    if (publicKeyBytes.length !== 32) {
      console.error(`Invalid public key length: ${publicKeyBytes.length} (expected 32)`);
      return false;
    }

    // Try WebCrypto first, fallback to noble
    if (await supportsWebCryptoEd25519()) {
      return verifyWithWebCrypto(signatureBytes, messageBytes, publicKeyBytes);
    } else {
      console.debug('WebCrypto Ed25519 not available, using @noble/ed25519 fallback');
      return verifyWithNoble(signatureBytes, messageBytes, publicKeyBytes);
    }
  } catch (error) {
    console.error('Signature verification failed:', error);
    return false;
  }
}

/**
 * Recursively sort keys in an object to match Python's json.dumps(sort_keys=True)
 */
function sortKeysDeep(obj: unknown): unknown {
  if (obj === null || typeof obj !== 'object') {
    return obj;
  }

  if (Array.isArray(obj)) {
    return obj.map(sortKeysDeep);
  }

  const sorted: Record<string, unknown> = {};
  const keys = Object.keys(obj as Record<string, unknown>).sort();
  for (const key of keys) {
    sorted[key] = sortKeysDeep((obj as Record<string, unknown>)[key]);
  }
  return sorted;
}

/**
 * Convert a value to JSON string matching Python's json.dumps(separators=(",",":")) compact format.
 * Backend signing scripts use compact separators (no spaces after : or ,).
 * JavaScript's JSON.stringify already uses this format, but we reimplement for sort_keys support.
 */
function toPythonJson(obj: unknown): string {
  if (obj === null) {
    return 'null';
  }
  if (typeof obj === 'boolean') {
    return obj ? 'true' : 'false';
  }
  if (typeof obj === 'number') {
    return String(obj);
  }
  if (typeof obj === 'string') {
    return JSON.stringify(obj); // handles escaping
  }
  if (Array.isArray(obj)) {
    const items = obj.map(toPythonJson);
    return '[' + items.join(',') + ']';
  }
  if (typeof obj === 'object') {
    const keys = Object.keys(obj).sort();
    const pairs = keys.map(k => JSON.stringify(k) + ':' + toPythonJson((obj as Record<string, unknown>)[k]));
    return '{' + pairs.join(',') + '}';
  }
  return String(obj);
}

/**
 * Verify plugin manifest signature
 *
 * Recreates canonical JSON matching backend signing format, then verifies signature.
 *
 * @param manifest - PluginManifest to verify
 * @returns true if signature is valid
 */
export async function verifyManifestSignature(manifest: PluginManifest): Promise<boolean> {
  if (!manifest.signature) {
    return false;
  }

  // Create canonical JSON (MUST match backend signing format)
  // Backend uses json.dumps(data, sort_keys=True) excluding signature fields
  // Also exclude is_encrypted which is a runtime-computed field added by the API
  const { signature, signature_pq: _signature_pq, is_encrypted: _is_encrypted, ...manifestWithoutSig } = manifest;

  // Recursively sort keys to match Python's sort_keys=True
  const canonicalObj = sortKeysDeep(manifestWithoutSig);

  // Use Python-compatible compact JSON format (no spaces after : and ,)
  const canonicalJson = toPythonJson(canonicalObj);
  const messageBytes = new TextEncoder().encode(canonicalJson);

  // Ed25519 verification (required)
  const ed25519Valid = await verifyEd25519Signature(signature, messageBytes);
  if (!ed25519Valid) return false;

  // ML-DSA-65 dual verification (required for v3+ manifests with signature_pq)
  if (manifest.signature_pq) {
    if (!DRYADE_PUBLIC_KEY_PQ_HEX) {
      console.error('ML-DSA-65 signature present but VITE_DRYADE_PUBLIC_KEY_PQ not configured — blocking plugin load (fail-closed)');
      return false;
    }
    const pqValid = await verifyMlDsa65Signature(
      manifest.signature_pq,
      messageBytes,
      DRYADE_PUBLIC_KEY_PQ_HEX
    );
    if (!pqValid) {
      console.error('ML-DSA-65 signature verification failed — blocking plugin load');
      return false;
    }
  }

  return true;
}

/**
 * Compute SHA-256 hash of content
 * Uses @noble/hashes for pure JS implementation (works without WebCrypto)
 *
 * @param content - String content to hash
 * @returns SHA-256 hash in format "sha256-{base64}" (SRI format)
 */
export async function computeSHA256(content: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(content);
  const hashArray = sha256(data);
  const base64Hash = btoa(String.fromCharCode(...hashArray));
  return `sha256-${base64Hash}`;
}

/**
 * Compute SHA-256 hash in hex format (matches backend)
 * Uses @noble/hashes for pure JS implementation (works without WebCrypto)
 */
export async function computeSHA256Hex(content: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(content);
  const hashArray = sha256(data);
  return Array.from(hashArray).map(b => b.toString(16).padStart(2, '0')).join('');
}
