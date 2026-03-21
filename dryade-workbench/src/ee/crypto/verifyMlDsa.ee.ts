// Licensed under the Dryade Enterprise Edition License. See LICENSE_EE.md.
// Licensed under LICENSE_EE.md -- see repository root

/**
 * ML-DSA-65 (FIPS 204) signature verification for browser-side plugin UI security.
 *
 * Uses @noble/post-quantum for pure JS ML-DSA-65 verification.
 * This runs BEFORE any untrusted plugin code enters the iframe sandbox.
 *
 * ML-DSA-65 constants:
 *   Signature: 3309 bytes (6618 hex chars)
 *   Public key: 1952 bytes (3904 hex chars)
 */

import { ml_dsa65 } from '@noble/post-quantum/ml-dsa.js';

const MLDSA65_SIG_SIZE = 3309;
const MLDSA65_PK_SIZE = 1952;

/**
 * Convert hex string to Uint8Array.
 * Returns null on invalid hex (odd length, non-hex chars).
 */
function hexToBytes(hex: string): Uint8Array | null {
  if (hex.length % 2 !== 0) return null;
  try {
    const bytes = new Uint8Array(hex.length / 2);
    for (let i = 0; i < bytes.length; i++) {
      const byte = parseInt(hex.substring(i * 2, i * 2 + 2), 16);
      if (isNaN(byte)) return null;
      bytes[i] = byte;
    }
    return bytes;
  } catch {
    return null;
  }
}

/**
 * Verify an ML-DSA-65 signature.
 *
 * @param signatureHex - Hex-encoded 3309-byte ML-DSA-65 signature
 * @param messageBytes - Message that was signed
 * @param publicKeyHex - Hex-encoded 1952-byte ML-DSA-65 public key
 * @returns true if signature is valid, false otherwise (never throws)
 */
export async function verifyMlDsa65Signature(
  signatureHex: string,
  messageBytes: Uint8Array,
  publicKeyHex: string
): Promise<boolean> {
  try {
    if (!signatureHex || !publicKeyHex) return false;

    const sigBytes = hexToBytes(signatureHex);
    const pkBytes = hexToBytes(publicKeyHex);

    if (!sigBytes || !pkBytes) return false;

    if (sigBytes.length !== MLDSA65_SIG_SIZE) {
      console.error(`Invalid ML-DSA-65 signature length: ${sigBytes.length} (expected ${MLDSA65_SIG_SIZE})`);
      return false;
    }
    if (pkBytes.length !== MLDSA65_PK_SIZE) {
      console.error(`Invalid ML-DSA-65 public key length: ${pkBytes.length} (expected ${MLDSA65_PK_SIZE})`);
      return false;
    }

    return ml_dsa65.verify(pkBytes, messageBytes, sigBytes);
  } catch (error) {
    console.error('ML-DSA-65 verification failed:', error);
    return false;
  }
}
