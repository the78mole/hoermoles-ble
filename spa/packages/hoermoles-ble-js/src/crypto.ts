/**
 * WebCrypto bindings: the one place in this package that touches
 * `crypto.subtle`, so `protocol.ts` can stay pure.
 *
 * The important design point is the non-extractable root key. A root key opens
 * a garage door; it is a physical capability, not a session token. Imported
 * with `extractable: false`, a `CryptoKey` can be stored in IndexedDB
 * (structured clone handles it) and used to sign commands forever, but its raw
 * bytes can never be read back out - not by this code, not by anything injected
 * into the page later. An attacker who gets script execution is reduced to a
 * signing oracle, which is worthless without physical BLE proximity to the drive.
 *
 * `importRootKeyExportable()` exists for the one case that genuinely needs the
 * bytes back (re-exporting a credential bundle to another device) and is
 * deliberately a separate, explicitly-named function rather than a boolean flag,
 * so the exportable path never happens by accident.
 */

import type { Signer } from './protocol.js';

const HMAC_PARAMS = { name: 'HMAC', hash: 'SHA-256' } as const;

/** Wraps a `CryptoKey` as the {@link Signer} the frame builders expect. */
export function signerFromKey(key: CryptoKey): Signer {
  return {
    async sign(message: Uint8Array): Promise<Uint8Array> {
      const signature = await crypto.subtle.sign('HMAC', key, message as BufferSource);
      return new Uint8Array(signature);
    },
  };
}

/** The default import path: the key can sign, and can never be read back. */
export function importRootKey(rootKey: Uint8Array): Promise<CryptoKey> {
  return crypto.subtle.importKey('raw', rootKey as BufferSource, HMAC_PARAMS, false, ['sign']);
}

/** Only for re-export. Prefer {@link importRootKey} everywhere else. */
export function importRootKeyExportable(rootKey: Uint8Array): Promise<CryptoKey> {
  return crypto.subtle.importKey('raw', rootKey as BufferSource, HMAC_PARAMS, true, ['sign']);
}

export async function exportRootKey(key: CryptoKey): Promise<Uint8Array> {
  if (!key.extractable) {
    throw new Error(
      'This credential was stored non-extractably and cannot be exported. ' +
        'Re-import it with "allow re-export" enabled if you need to move it.',
    );
  }
  return new Uint8Array(await crypto.subtle.exportKey('raw', key));
}

/** Convenience for the registration flow, where the register key is ephemeral
 * and lives only for the duration of the handshake. */
export async function signerFromBytes(keyBytes: Uint8Array): Promise<Signer> {
  return signerFromKey(await importRootKey(keyBytes));
}

export function randomBytes(length: number): Uint8Array {
  return crypto.getRandomValues(new Uint8Array(length));
}

// --- Passphrase encryption for credential bundles -------------------------
// Must stay bit-compatible with bundle.py's `_derive_key`/`encode_bundle`.

export const PBKDF2_ITERATIONS = 600_000;

export async function deriveBundleKey(passphrase: string, salt: Uint8Array): Promise<CryptoKey> {
  const material = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(passphrase) as BufferSource,
    'PBKDF2',
    false,
    ['deriveKey'],
  );
  return crypto.subtle.deriveKey(
    { name: 'PBKDF2', salt: salt as BufferSource, iterations: PBKDF2_ITERATIONS, hash: 'SHA-256' },
    material,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt'],
  );
}

export async function aesGcmEncrypt(
  key: CryptoKey,
  nonce: Uint8Array,
  plaintext: Uint8Array,
  additionalData: Uint8Array,
): Promise<Uint8Array> {
  const result = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv: nonce as BufferSource, additionalData: additionalData as BufferSource },
    key,
    plaintext as BufferSource,
  );
  return new Uint8Array(result);
}

export async function aesGcmDecrypt(
  key: CryptoKey,
  nonce: Uint8Array,
  ciphertext: Uint8Array,
  additionalData: Uint8Array,
): Promise<Uint8Array> {
  const result = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: nonce as BufferSource, additionalData: additionalData as BufferSource },
    key,
    ciphertext as BufferSource,
  );
  return new Uint8Array(result);
}
