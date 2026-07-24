/**
 * Credential bundle - the TypeScript half of the format defined in
 * `python/packages/hoermoles-ble/src/hoermoles_ble/bundle.py`. The two files
 * implement one spec; change them together.
 *
 *     HMOLES1:<base64url(utf8 json)>            plaintext
 *     HMOLES1E:<base64url(binary envelope)>     passphrase-encrypted
 *
 * Encrypted envelope: `"HM1E" || salt(16) || nonce(12) || AES-256-GCM(ct||tag)`,
 * key via PBKDF2-HMAC-SHA256 with 600k iterations, the magic doubling as the
 * AEAD's additional data.
 *
 * `serial_no` is a **string** on the wire and stays one here. Hoermann serials
 * are uint64 (302626026414510307 on the live test device) and exceed
 * `Number.MAX_SAFE_INTEGER`, so `JSON.parse` would round the last digits away.
 * Never coerce it to a number - use it as a string, or `BigInt(...)` it.
 */

import { concatBytes, fromBase64Url, fromHex, fromUtf8, toBase64Url, toHex, utf8 } from './bytes.js';
import { aesGcmDecrypt, aesGcmEncrypt, deriveBundleKey, randomBytes } from './crypto.js';

export const BUNDLE_FORMAT = 'hoermoles-credentials';
export const BUNDLE_VERSION = 1;
export const PREFIX_PLAIN = 'HMOLES1:';
export const PREFIX_ENCRYPTED = 'HMOLES1E:';

const ENCRYPTED_MAGIC = utf8('HM1E');
const SALT_SIZE = 16;
const NONCE_SIZE = 12;

export class BundleError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'BundleError';
  }
}

/** One drive. `rootKey` is raw key material - hand it to `importRootKey()` and
 * drop the bytes as soon as possible; do not keep it in application state. */
export interface BundleEntry {
  deviceAddress: string;
  rootId: number;
  rootKey: Uint8Array;
  qrPrefix: string;
  createdUnix: number;
  /** User-chosen display name. Carried independently of the product metadata so
   * a renamed drive survives export/import, including through the CLI. */
  label?: string | null;
  productClass?: number;
  productId?: number;
  productName?: string | null;
  /** uint64 as a decimal string - see the module docstring. */
  serialNo?: string | null;
}

interface RawEntry {
  device_address: string;
  root_id: number;
  root_key_hex: string;
  qr_prefix?: string;
  created_unix?: number;
  label?: string | null;
  product_class?: number;
  product_id?: number;
  product_name?: string | null;
  /** String on the wire; a number only in bundles written before that change. */
  serial_no?: string | number | null;
}

interface RawBundle {
  format?: string;
  v?: number;
  devices?: RawEntry[];
}

function toRaw(entry: BundleEntry): RawEntry {
  const raw: RawEntry = {
    device_address: entry.deviceAddress.toUpperCase(),
    root_id: entry.rootId,
    root_key_hex: toHex(entry.rootKey),
    qr_prefix: entry.qrPrefix ?? '',
    created_unix: entry.createdUnix ?? 0,
  };
  // Only emit a label when there is one, so unnamed drives keep clean bundles.
  if (entry.label) raw.label = entry.label;
  if (entry.productClass !== undefined && entry.productId !== undefined) {
    raw.product_class = entry.productClass;
    raw.product_id = entry.productId;
    raw.product_name = entry.productName ?? null;
    raw.serial_no = entry.serialNo ?? null;
  }
  return raw;
}

/** Legacy bundles carried the serial as a JSON number; those are already
 * rounded by the time we see them, but importing something is better than
 * rejecting the whole bundle over a cosmetic field. */
function normalizeSerial(value: string | number | null | undefined): string | null {
  if (value === null || value === undefined) return null;
  return String(value);
}

function fromRaw(raw: RawEntry): BundleEntry {
  if (typeof raw?.device_address !== 'string' || typeof raw?.root_key_hex !== 'string') {
    throw new BundleError('Malformed bundle entry: missing device_address or root_key_hex');
  }
  let rootKey: Uint8Array;
  try {
    rootKey = fromHex(raw.root_key_hex);
  } catch (error) {
    throw new BundleError(`Malformed bundle entry: ${(error as Error).message}`);
  }
  const entry: BundleEntry = {
    deviceAddress: raw.device_address,
    rootId: Number(raw.root_id),
    rootKey,
    qrPrefix: raw.qr_prefix ?? '',
    createdUnix: Number(raw.created_unix ?? 0),
  };
  if (typeof raw.label === 'string' && raw.label !== '') entry.label = raw.label;
  if (raw.product_class != null && raw.product_id != null) {
    entry.productClass = Number(raw.product_class);
    entry.productId = Number(raw.product_id);
    entry.productName = raw.product_name ?? null;
    entry.serialNo = normalizeSerial(raw.serial_no);
  }
  return entry;
}

export function buildBundle(entries: readonly BundleEntry[]): RawBundle {
  return { format: BUNDLE_FORMAT, v: BUNDLE_VERSION, devices: entries.map(toRaw) };
}

export function parseBundle(payload: unknown): BundleEntry[] {
  const bundle = payload as RawBundle;
  if (typeof bundle !== 'object' || bundle === null)
    throw new BundleError('Bundle must be a JSON object.');
  if (bundle.format !== BUNDLE_FORMAT) {
    throw new BundleError(
      `Not a hoermoles credential bundle (format=${JSON.stringify(bundle.format)}).`,
    );
  }
  if (bundle.v !== BUNDLE_VERSION) {
    throw new BundleError(
      `Unsupported bundle version ${JSON.stringify(bundle.v)}, this build understands v${BUNDLE_VERSION}.`,
    );
  }
  if (!Array.isArray(bundle.devices)) throw new BundleError("Bundle is missing a 'devices' list.");
  return bundle.devices.map(fromRaw);
}

/** File form: pretty JSON, matching what the CLI's `export --out` writes. */
export function bundleToJson(entries: readonly BundleEntry[]): string {
  return JSON.stringify(buildBundle(entries), null, 2) + '\n';
}

export function bundleFromJson(text: string): BundleEntry[] {
  let payload: unknown;
  try {
    payload = JSON.parse(text);
  } catch (error) {
    throw new BundleError(`Not valid JSON: ${(error as Error).message}`);
  }
  return parseBundle(payload);
}

export function isEncryptedBundle(text: string): boolean {
  return text.trim().startsWith(PREFIX_ENCRYPTED);
}

/** Text form for QR codes and URL fragments. Passing a passphrase selects the
 * encrypted form - do that for anything leaving the device. */
export async function encodeBundle(
  entries: readonly BundleEntry[],
  passphrase?: string,
): Promise<string> {
  const raw = utf8(JSON.stringify(buildBundle(entries)));
  if (passphrase === undefined) return PREFIX_PLAIN + toBase64Url(raw);

  const salt = randomBytes(SALT_SIZE);
  const nonce = randomBytes(NONCE_SIZE);
  const key = await deriveBundleKey(passphrase, salt);
  const ciphertext = await aesGcmEncrypt(key, nonce, raw, ENCRYPTED_MAGIC);
  return PREFIX_ENCRYPTED + toBase64Url(concatBytes(ENCRYPTED_MAGIC, salt, nonce, ciphertext));
}

/** Accepts every form a bundle arrives in: both text prefixes, raw JSON, or a
 * full `https://.../#import=...` URL (users paste the whole link). */
export async function decodeBundle(text: string, passphrase?: string): Promise<BundleEntry[]> {
  let payload = text.trim();
  const fragmentIndex = payload.indexOf('#import=');
  if (fragmentIndex !== -1) payload = payload.slice(fragmentIndex + '#import='.length).trim();

  if (payload.startsWith(PREFIX_ENCRYPTED)) {
    if (passphrase === undefined)
      throw new BundleError('This bundle is encrypted - a passphrase is required.');
    let envelope: Uint8Array;
    try {
      envelope = fromBase64Url(payload.slice(PREFIX_ENCRYPTED.length));
    } catch (error) {
      throw new BundleError(`Malformed base64url payload: ${(error as Error).message}`);
    }
    const offset = ENCRYPTED_MAGIC.length;
    const magicMatches = ENCRYPTED_MAGIC.every((byte, i) => envelope[i] === byte);
    if (envelope.length <= offset + SALT_SIZE + NONCE_SIZE || !magicMatches) {
      throw new BundleError('Malformed encrypted bundle envelope.');
    }
    const salt = envelope.subarray(offset, offset + SALT_SIZE);
    const nonce = envelope.subarray(offset + SALT_SIZE, offset + SALT_SIZE + NONCE_SIZE);
    const ciphertext = envelope.subarray(offset + SALT_SIZE + NONCE_SIZE);
    let plaintext: Uint8Array;
    try {
      const key = await deriveBundleKey(passphrase, salt);
      plaintext = await aesGcmDecrypt(key, nonce, ciphertext, ENCRYPTED_MAGIC);
    } catch {
      throw new BundleError('Could not decrypt the bundle - wrong passphrase or corrupted data.');
    }
    return bundleFromJson(fromUtf8(plaintext));
  }

  if (payload.startsWith(PREFIX_PLAIN)) {
    let decoded: Uint8Array;
    try {
      decoded = fromBase64Url(payload.slice(PREFIX_PLAIN.length));
    } catch (error) {
      throw new BundleError(`Malformed base64url payload: ${(error as Error).message}`);
    }
    return bundleFromJson(fromUtf8(decoded));
  }

  if (payload.startsWith('{')) return bundleFromJson(payload);

  throw new BundleError(
    `Unrecognized bundle format - expected '${PREFIX_PLAIN}', '${PREFIX_ENCRYPTED}' or JSON.`,
  );
}
