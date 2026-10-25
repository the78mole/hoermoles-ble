/**
 * Key handoff to Home Assistant - the client half of the protocol whose server
 * half is `custom_components/hoermoles_ble/handoff.py` in
 * the78mole/hoermoles-ble-homeassistant (spec: that repo's docs/key-handoff.md).
 * The two files implement one spec; change them together, and regenerate
 * `shared/handoff-vectors.json` there.
 *
 * HA's config flow shows a QR code that opens this app with
 *
 *     #ha=<base64url(JSON {v, u, k, a, n})>
 *
 * `k` is an ephemeral P-256 key that only exists inside that one config flow.
 * The app encrypts a plaintext `HMOLES1:` bundle to it and *navigates* to
 * `u#p=<base64url(envelope)>` - a top-level navigation, which neither
 * `connect-src 'none'` nor `form-action 'none'` governs, so the CSP stays as
 * strict as it is. HA's page at `u` posts the fragment back to itself.
 *
 * Envelope: `"HM1H" || client_pub(65) || nonce(12) || AES-256-GCM(ct||tag)`,
 * key = HKDF-SHA256(ECDH(client, k), salt = k || client_pub,
 * info = "hoermoles-ha-handoff-v1"), AAD = `"HM1H" || token`.
 */

import { concatBytes, fromBase64Url, fromUtf8, toBase64Url, utf8 } from './bytes.js';
import { aesGcmEncrypt, randomBytes } from './crypto.js';

export const HANDOFF_VERSION = 1;
export const HANDOFF_MARKER = '#ha=';

const MAGIC = utf8('HM1H');
const HKDF_INFO = utf8('hoermoles-ha-handoff-v1');
const PUBLIC_KEY_SIZE = 65;
const NONCE_SIZE = 12;
const ECDH_P256 = { name: 'ECDH', namedCurve: 'P-256' } as const;

/** HA's handoff endpoint. The token is `secrets.token_urlsafe(32)`. Anything
 * else is not a Home Assistant handoff URL, whatever the QR code claims. */
const HANDOFF_PATH = /\/api\/hoermoles_ble\/handoff\/([A-Za-z0-9_-]{43})$/;
const MAC_ADDRESS = /^([0-9A-F]{2}:){5}[0-9A-F]{2}$/;

export class HandoffError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'HandoffError';
  }
}

/** A parsed `#ha=` request: where to send which drive's key, encrypted to what. */
export interface HandoffRequest {
  /** One-time target URL, without fragment. */
  url: string;
  /** Last path segment of {@link url}; bound into the ciphertext as AAD. */
  token: string;
  /** HA's ephemeral public key, 65-byte uncompressed P-256 point. */
  publicKey: Uint8Array;
  /** The drive HA is setting up, upper case. HA rejects any other. */
  address: string;
  /** HA's location name - display only, never trust it. */
  name: string;
  /** `host[:port]` of {@link url}, which is what the user must check. */
  host: string;
  secure: boolean;
  /** Whether the host is a LAN/loopback/.local address (see {@link isPrivateHost}). */
  privateHost: boolean;
}

interface RawRequest {
  v?: unknown;
  u?: unknown;
  k?: unknown;
  a?: unknown;
  n?: unknown;
}

/**
 * Hosts a Home Assistant QR code normally points at. A public host is not
 * necessarily wrong (a reverse proxy, a DynDNS name), but it is also exactly
 * what a planted QR code would use, so the UI warns about it.
 */
export function isPrivateHost(hostname: string): boolean {
  const host = hostname.toLowerCase().replace(/^\[|\]$/g, '');
  if (host === 'localhost' || /\.(local|lan|home\.arpa|internal)$/.test(host)) return true;

  const ipv4 = host.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
  if (ipv4) {
    const [a, b] = [Number(ipv4[1]), Number(ipv4[2])];
    return (
      a === 10 ||
      a === 127 ||
      (a === 172 && b >= 16 && b <= 31) ||
      (a === 192 && b === 168) ||
      (a === 169 && b === 254) ||
      (a === 100 && b >= 64 && b <= 127) // CGNAT, which is also where Tailscale lives
    );
  }
  if (host.includes(':')) {
    return host === '::1' || /^f[cd][0-9a-f]{2}:/.test(host) || /^fe[89ab][0-9a-f]:/.test(host);
  }
  return false;
}

/**
 * Extracts a handoff request from whatever was scanned or opened: the full app
 * link, just its fragment, or `#ha=...` on its own. Returns `null` when the
 * text is not a handoff link at all, so callers can fall through to bundle
 * import; throws {@link HandoffError} when it is one but is malformed.
 */
export function parseHandoffLink(text: string): HandoffRequest | null {
  const marker = text.indexOf(HANDOFF_MARKER);
  if (marker === -1) return null;
  const encoded = text.slice(marker + HANDOFF_MARKER.length).trim();

  let raw: RawRequest;
  try {
    raw = JSON.parse(fromUtf8(fromBase64Url(encoded))) as RawRequest;
  } catch {
    throw new HandoffError('This Home Assistant QR code is damaged - scan it again.');
  }
  if (typeof raw !== 'object' || raw === null) throw new HandoffError('Malformed handoff request.');
  if (raw.v !== HANDOFF_VERSION) {
    throw new HandoffError(
      `Unsupported handoff version ${JSON.stringify(raw.v)} - update this app or the integration.`,
    );
  }

  let url: URL;
  try {
    url = new URL(String(raw.u));
  } catch {
    throw new HandoffError('The handoff request has no valid target URL.');
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    throw new HandoffError(`Refusing to send a key to a ${url.protocol} URL.`);
  }
  if (url.username || url.password || url.search || url.hash) {
    throw new HandoffError('The target URL does not look like a Home Assistant handoff URL.');
  }
  const token = url.pathname.match(HANDOFF_PATH)?.[1];
  if (!token) throw new HandoffError('The target URL does not look like a Home Assistant handoff URL.');

  let publicKey: Uint8Array;
  try {
    publicKey = fromBase64Url(String(raw.k));
  } catch {
    throw new HandoffError('The handoff request carries no valid key.');
  }
  if (publicKey.length !== PUBLIC_KEY_SIZE || publicKey[0] !== 0x04) {
    throw new HandoffError('The handoff request carries no valid key.');
  }

  const address = String(raw.a ?? '').toUpperCase();
  if (!MAC_ADDRESS.test(address)) throw new HandoffError('The handoff request names no valid drive.');

  return {
    url: url.href,
    token,
    publicKey,
    address,
    name: typeof raw.n === 'string' ? raw.n : '',
    host: url.host,
    secure: url.protocol === 'https:',
    privateHost: isPrivateHost(url.hostname),
  };
}

async function deriveHandoffKey(
  privateKey: CryptoKey,
  haPublic: Uint8Array,
  clientPublic: Uint8Array,
): Promise<CryptoKey> {
  const peer = await crypto.subtle.importKey('raw', haPublic as BufferSource, ECDH_P256, false, []);
  const shared = await crypto.subtle.deriveBits({ name: 'ECDH', public: peer }, privateKey, 256);
  const ikm = await crypto.subtle.importKey('raw', shared, 'HKDF', false, ['deriveKey']);
  return crypto.subtle.deriveKey(
    {
      name: 'HKDF',
      hash: 'SHA-256',
      salt: concatBytes(haPublic, clientPublic) as BufferSource,
      info: HKDF_INFO as BufferSource,
    },
    ikm,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt'],
  );
}

/**
 * Encrypts `plaintext` (a `HMOLES1:` bundle text) for the HA flow behind
 * `request`. `fixed` exists only so the test vector can pin the otherwise
 * random client key and nonce - never pass it in application code.
 */
export async function encryptHandoff(
  request: Pick<HandoffRequest, 'publicKey' | 'token'>,
  plaintext: string,
  fixed: { clientKeyPair?: CryptoKeyPair; nonce?: Uint8Array } = {},
): Promise<Uint8Array> {
  const client =
    fixed.clientKeyPair ?? (await crypto.subtle.generateKey(ECDH_P256, false, ['deriveBits']));
  const clientPublic = new Uint8Array(await crypto.subtle.exportKey('raw', client.publicKey));
  const key = await deriveHandoffKey(client.privateKey, request.publicKey, clientPublic);
  const nonce = fixed.nonce ?? randomBytes(NONCE_SIZE);
  const aad = concatBytes(MAGIC, utf8(request.token));
  const ciphertext = await aesGcmEncrypt(key, nonce, utf8(plaintext), aad);
  return concatBytes(MAGIC, clientPublic, nonce, ciphertext);
}

/** Where to navigate to deliver `envelope`. The fragment never leaves the
 * phone in the request itself; HA's page reads it and posts it back. */
export function handoffDeliveryUrl(request: Pick<HandoffRequest, 'url'>, envelope: Uint8Array): string {
  return `${request.url}#p=${toBase64Url(envelope)}`;
}
