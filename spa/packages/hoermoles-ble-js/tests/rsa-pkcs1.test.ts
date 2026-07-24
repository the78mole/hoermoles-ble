/**
 * RSAES-PKCS#1 v1.5 encryption - the piece WebCrypto refuses to provide.
 *
 * Because v1.5 padding is randomised, ciphertexts cannot be compared against a
 * fixed vector. The meaningful test is a decryption round trip: generate an RSA
 * key pair, encrypt with our implementation, and decrypt with an independent
 * one. WebCrypto cannot decrypt v1.5 either, so the check is done directly on
 * the RSA primitive - `m = c^d mod n` using the private exponent from the JWK -
 * followed by unpadding. If our padding or our modular exponentiation were
 * wrong, the recovered message would not match.
 */

import { describe, expect, it } from 'vitest';

import { fromBase64Url, toHex } from '../src/bytes.js';
import {
  _internal,
  loadDevicePublicKey,
  modPow,
  padPkcs1v15Type2,
  rsaPkcs1v15Encrypt,
} from '../src/rsa-pkcs1.js';

const { bytesToBigInt, bigIntToBytes } = _internal;

async function generateKeyPair(modulusLength = 2048) {
  return crypto.subtle.generateKey(
    {
      name: 'RSA-OAEP', // only a vehicle - we never use WebCrypto's own encryption here
      modulusLength,
      publicExponent: new Uint8Array([0x01, 0x00, 0x01]),
      hash: 'SHA-256',
    },
    true,
    ['encrypt', 'decrypt'],
  );
}

/** Raw RSA decryption plus PKCS#1 v1.5 type-2 unpadding, used only to verify
 * what our encrypt produced. */
async function decryptPkcs1v15(privateKey: CryptoKey, ciphertext: Uint8Array): Promise<Uint8Array> {
  const jwk = await crypto.subtle.exportKey('jwk', privateKey);
  const n = bytesToBigInt(fromBase64Url(jwk.n!));
  const d = bytesToBigInt(fromBase64Url(jwk.d!));
  const modulusSize = fromBase64Url(jwk.n!).length;

  const block = bigIntToBytes(modPow(bytesToBigInt(ciphertext), d, n), modulusSize);
  expect(block[0]).toBe(0x00);
  expect(block[1]).toBe(0x02);

  const separator = block.indexOf(0x00, 2);
  expect(separator).toBeGreaterThan(9); // at least 8 padding bytes, per the spec
  return block.subarray(separator + 1);
}

describe('rsaPkcs1v15Encrypt', () => {
  it('round-trips a 32-byte register key through a real RSA key pair', async () => {
    const keyPair = await generateKeyPair();
    const spki = new Uint8Array(await crypto.subtle.exportKey('spki', keyPair.publicKey));
    const publicKey = await loadDevicePublicKey(spki);

    const registerKey = crypto.getRandomValues(new Uint8Array(32));
    const ciphertext = rsaPkcs1v15Encrypt(publicKey, registerKey);

    expect(ciphertext.length).toBe(256); // always the modulus size
    expect(toHex(await decryptPkcs1v15(keyPair.privateKey, ciphertext))).toBe(toHex(registerKey));
  });

  it('produces a different ciphertext every time (randomised padding)', async () => {
    const keyPair = await generateKeyPair();
    const spki = new Uint8Array(await crypto.subtle.exportKey('spki', keyPair.publicKey));
    const publicKey = await loadDevicePublicKey(spki);
    const message = new Uint8Array(32).fill(0x42);

    expect(toHex(rsaPkcs1v15Encrypt(publicKey, message))).not.toBe(
      toHex(rsaPkcs1v15Encrypt(publicKey, message)),
    );
  });

  it('works with a 1024-bit modulus too', async () => {
    const keyPair = await generateKeyPair(1024);
    const spki = new Uint8Array(await crypto.subtle.exportKey('spki', keyPair.publicKey));
    const publicKey = await loadDevicePublicKey(spki);

    const message = crypto.getRandomValues(new Uint8Array(32));
    const ciphertext = rsaPkcs1v15Encrypt(publicKey, message);
    expect(ciphertext.length).toBe(128);
    expect(toHex(await decryptPkcs1v15(keyPair.privateKey, ciphertext))).toBe(toHex(message));
  });

  it('reads modulus and exponent out of a SubjectPublicKeyInfo blob', async () => {
    const keyPair = await generateKeyPair();
    const spki = new Uint8Array(await crypto.subtle.exportKey('spki', keyPair.publicKey));
    const publicKey = await loadDevicePublicKey(spki);

    expect(publicKey.e).toBe(65537n);
    expect(publicKey.sizeBytes).toBe(256);
    expect(publicKey.n.toString(2).length).toBe(2048);
  });

  it('rejects a non-RSA SubjectPublicKeyInfo', async () => {
    const ed25519Spki = new Uint8Array([
      0x30,
      0x2a,
      0x30,
      0x05,
      0x06,
      0x03,
      0x2b,
      0x65,
      0x70,
      0x03,
      0x21,
      0x00,
      ...new Array(32).fill(0x11),
    ]);
    await expect(loadDevicePublicKey(ed25519Spki)).rejects.toThrow();
  });
});

describe('padPkcs1v15Type2', () => {
  it('builds 0x00 || 0x02 || PS || 0x00 || M with non-zero padding', () => {
    const message = new Uint8Array([1, 2, 3, 4]);
    const block = padPkcs1v15Type2(message, 128);

    expect(block.length).toBe(128);
    expect(block[0]).toBe(0x00);
    expect(block[1]).toBe(0x02);

    const separator = block.indexOf(0x00, 2);
    expect(separator).toBe(128 - message.length - 1);
    // A zero byte inside PS would fake an early terminator and truncate the
    // message - the loop that resamples zeros exists precisely for this.
    expect(block.subarray(2, separator).includes(0)).toBe(false);
    expect([...block.subarray(separator + 1)]).toEqual([1, 2, 3, 4]);
  });

  it('refuses a message too long for the modulus', () => {
    // 128-byte modulus needs 3 framing bytes + at least 8 padding bytes.
    expect(() => padPkcs1v15Type2(new Uint8Array(118), 128)).toThrow(/too long/);
    expect(() => padPkcs1v15Type2(new Uint8Array(117), 128)).not.toThrow();
  });
});

describe('modPow', () => {
  it('matches hand-computed values', () => {
    expect(modPow(2n, 10n, 1000n)).toBe(24n);
    expect(modPow(5n, 0n, 7n)).toBe(1n);
    expect(modPow(3n, 1n, 7n)).toBe(3n);
  });

  it('handles bases larger than the modulus', () => {
    expect(modPow(123n, 3n, 7n)).toBe(123n ** 3n % 7n);
  });
});

describe('big-integer conversion', () => {
  it('round-trips big-endian bytes', () => {
    const bytes = crypto.getRandomValues(new Uint8Array(64));
    expect(toHex(bigIntToBytes(bytesToBigInt(bytes), 64))).toBe(toHex(bytes));
  });

  it('left-pads to the requested length', () => {
    expect(toHex(bigIntToBytes(1n, 4))).toBe('00000001');
  });

  it('refuses a value that does not fit', () => {
    expect(() => bigIntToBytes(0x1_0000n, 2)).toThrow(/does not fit/);
  });
});
