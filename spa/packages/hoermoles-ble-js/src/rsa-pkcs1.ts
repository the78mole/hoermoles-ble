/**
 * RSAES-PKCS#1 v1.5 encryption - the one piece of the registration handshake
 * WebCrypto cannot do for us.
 *
 * WebCrypto deliberately omits PKCS#1 v1.5 *encryption* (it offers RSA-OAEP for
 * encryption and RSASSA-PKCS1-v1_5 only for signing). The drive, however,
 * expects exactly v1.5: the original is `HAL.Android.RSA.RSAEngine.Encrypt(data,
 * fOAEP: false)`, i.e. the mbedTLS `MBEDTLS_RSA_PKCS_V15` equivalent. So we do
 * it by hand.
 *
 * "By hand" here is only the padding and the modular exponentiation. Parsing the
 * SubjectPublicKeyInfo DER out of the QR code is delegated to WebCrypto itself -
 * importing the key as RSA-OAEP and exporting it as JWK yields the modulus and
 * exponent already decoded, which is far more trustworthy than a hand-written
 * ASN.1 walker.
 *
 * Security note: this is *encryption to the device's public key* with a freshly
 * generated 32-byte register key. Encrypting-only with v1.5 does not expose us
 * to the Bleichenbacher padding-oracle attacks that make v1.5 *decryption*
 * dangerous - there is no decryption oracle on our side at all.
 */

import { fromBase64Url } from './bytes.js';

function bytesToBigInt(bytes: Uint8Array): bigint {
  let result = 0n;
  for (const byte of bytes) result = (result << 8n) | BigInt(byte);
  return result;
}

function bigIntToBytes(value: bigint, length: number): Uint8Array {
  const result = new Uint8Array(length);
  let remaining = value;
  for (let i = length - 1; i >= 0; i--) {
    result[i] = Number(remaining & 0xffn);
    remaining >>= 8n;
  }
  if (remaining !== 0n) throw new Error('Value does not fit into the requested length');
  return result;
}

/** Square-and-multiply. With the usual e=65537 this runs 17 iterations, so
 * there is no reason to reach for anything fancier. */
export function modPow(base: bigint, exponent: bigint, modulus: bigint): bigint {
  let result = 1n;
  let b = base % modulus;
  let e = exponent;
  while (e > 0n) {
    if (e & 1n) result = (result * b) % modulus;
    b = (b * b) % modulus;
    e >>= 1n;
  }
  return result;
}

export interface RsaPublicKey {
  n: bigint;
  e: bigint;
  /** Modulus length in bytes - the size of every ciphertext this key produces. */
  sizeBytes: number;
}

/** Recovers (n, e) from a SubjectPublicKeyInfo DER blob by round-tripping it
 * through WebCrypto's own parser. The RSA-OAEP algorithm name is only a vehicle
 * for the import - we never use the resulting key to encrypt. */
export async function loadDevicePublicKey(spkiDer: Uint8Array): Promise<RsaPublicKey> {
  const key = await crypto.subtle.importKey(
    'spki',
    spkiDer as BufferSource,
    { name: 'RSA-OAEP', hash: 'SHA-256' },
    true,
    ['encrypt'],
  );
  const jwk = await crypto.subtle.exportKey('jwk', key);
  if (!jwk.n || !jwk.e)
    throw new Error('Public key did not expose a modulus/exponent (not an RSA key?)');
  const modulusBytes = fromBase64Url(jwk.n);
  return {
    n: bytesToBigInt(modulusBytes),
    e: bytesToBigInt(fromBase64Url(jwk.e)),
    sizeBytes: modulusBytes.length,
  };
}

/**
 * EME-PKCS1-v1_5 encryption block: `0x00 || 0x02 || PS || 0x00 || M`, where PS
 * is `k - mLen - 3` random **non-zero** bytes (the zero byte is the terminator,
 * so a zero inside PS would corrupt the message boundary).
 *
 * Exported for testing - callers want {@link rsaPkcs1v15Encrypt}.
 */
export function padPkcs1v15Type2(message: Uint8Array, modulusSizeBytes: number): Uint8Array {
  const psLength = modulusSizeBytes - message.length - 3;
  if (psLength < 8) {
    throw new Error(
      `Message of ${message.length} bytes is too long for a ${modulusSizeBytes}-byte modulus ` +
        '(PKCS#1 v1.5 needs at least 8 padding bytes)',
    );
  }

  const padding = crypto.getRandomValues(new Uint8Array(psLength));
  for (let i = 0; i < padding.length; i++) {
    while (padding[i] === 0) padding[i] = crypto.getRandomValues(new Uint8Array(1))[0];
  }

  const block = new Uint8Array(modulusSizeBytes);
  block[0] = 0x00;
  block[1] = 0x02;
  block.set(padding, 2);
  block[2 + padding.length] = 0x00;
  block.set(message, 3 + padding.length);
  return block;
}

/** Encrypts `message` (for us: the 32-byte register key) to the drive's public
 * key. Output is always `sizeBytes` long, as the protocol expects. */
export function rsaPkcs1v15Encrypt(publicKey: RsaPublicKey, message: Uint8Array): Uint8Array {
  const block = padPkcs1v15Type2(message, publicKey.sizeBytes);
  const ciphertext = modPow(bytesToBigInt(block), publicKey.e, publicKey.n);
  return bigIntToBytes(ciphertext, publicKey.sizeBytes);
}

export const _internal = { bytesToBigInt, bigIntToBytes };
