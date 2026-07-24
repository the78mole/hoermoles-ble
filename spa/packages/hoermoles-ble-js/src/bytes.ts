/**
 * Byte helpers. Nothing here is Hoermann-specific - it exists because
 * `Uint8Array` has no concat, no hex, and no unpadded base64url, and the
 * protocol code reads far better without those details inlined.
 */

export function concatBytes(...parts: Uint8Array[]): Uint8Array {
  const total = parts.reduce((sum, part) => sum + part.length, 0);
  const result = new Uint8Array(total);
  let offset = 0;
  for (const part of parts) {
    result.set(part, offset);
    offset += part.length;
  }
  return result;
}

export function toHex(data: Uint8Array): string {
  let hex = '';
  for (const byte of data) hex += byte.toString(16).padStart(2, '0');
  return hex;
}

export function fromHex(hex: string): Uint8Array {
  const clean = hex.trim();
  if (clean.length % 2 !== 0) throw new Error(`Hex string of odd length: ${clean.length}`);
  const result = new Uint8Array(clean.length / 2);
  for (let i = 0; i < result.length; i++) {
    const byte = Number.parseInt(clean.slice(i * 2, i * 2 + 2), 16);
    if (Number.isNaN(byte)) throw new Error(`Not a hex string: ${hex}`);
    result[i] = byte;
  }
  return result;
}

export function uint16LE(value: number): Uint8Array {
  const bytes = new Uint8Array(2);
  new DataView(bytes.buffer).setUint16(0, value, true);
  return bytes;
}

export function uint64LE(value: number | bigint): Uint8Array {
  const bytes = new Uint8Array(8);
  new DataView(bytes.buffer).setBigUint64(0, BigInt(value), true);
  return bytes;
}

/** A DataView over exactly `data`, honouring its byteOffset - a plain
 * `new DataView(data.buffer)` silently reads the whole backing buffer and is a
 * classic source of off-by-N bugs when the array came from `subarray()`. */
export function viewOf(data: Uint8Array): DataView {
  return new DataView(data.buffer, data.byteOffset, data.byteLength);
}

export function readUint16LE(data: Uint8Array, offset: number): number {
  return viewOf(data).getUint16(offset, true);
}

export function readInt16LE(data: Uint8Array, offset: number): number {
  return viewOf(data).getInt16(offset, true);
}

export function readUint32LE(data: Uint8Array, offset: number): number {
  return viewOf(data).getUint32(offset, true);
}

export function utf8(text: string): Uint8Array {
  return new TextEncoder().encode(text);
}

export function fromUtf8(data: Uint8Array): string {
  return new TextDecoder().decode(data);
}

/** base64url without padding - safe inside a URL fragment, which is how
 * credential bundles travel. Mirrors bundle.py's `_b64url_encode`. */
export function toBase64Url(data: Uint8Array): string {
  let binary = '';
  for (const byte of data) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export function fromBase64Url(text: string): Uint8Array {
  const normalized = text.replace(/-/g, '+').replace(/_/g, '/');
  const padded = normalized + '='.repeat((4 - (normalized.length % 4)) % 4);
  const binary = atob(padded);
  const result = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) result[i] = binary.charCodeAt(i);
  return result;
}

/** Constant-time-ish equality. Used for nothing security-critical today, but
 * comparing MACs with `===` on hex strings is a habit worth not forming. */
export function bytesEqual(a: Uint8Array, b: Uint8Array): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a[i] ^ b[i];
  return diff === 0;
}
