/**
 * Pure protocol logic for the Hoermann BlueSecur "Signed" BLE channel.
 *
 * Direct port of `python/packages/hoermoles-ble/src/hoermoles_ble/protocol.py` -
 * that module is the reference implementation and carries the full commentary
 * on where each field comes from in the decompiled app. Read it alongside this
 * file; the comments here only cover what differs in TypeScript.
 *
 * Like the Python original this module has no I/O and no library dependencies.
 * The one structural difference: HMAC-SHA256 is asynchronous in the browser
 * (WebCrypto), so every frame builder is `async` and takes a {@link Signer}
 * rather than raw key bytes. That also keeps WebCrypto itself out of this file
 * (see `crypto.ts`) and lets the root key live as a non-extractable `CryptoKey`.
 *
 * Both directions are byte-verified against `shared/test-vectors.json`, which is
 * generated from the Python implementation - see `hoermoles_ble.interop`.
 */

import {
  concatBytes,
  readInt16LE,
  readUint16LE,
  readUint32LE,
  uint16LE,
  uint64LE,
  utf8,
} from './bytes.js';

export const BC_SERVICE = '669a9001-0008-968f-e311-6050405558b3';
export const BC_TX = '669a900c-0008-968f-e311-6050405558b3';
export const BC_RX = '669a900a-0008-968f-e311-6050405558b3';

export const GATT_WRITE_CHUNK_SIZE = 20;

export const ROUTING_SIGNED = 0x01;
export const ROUTING_ENCRYPTED = 0x02;
export const ROUTING_BLUECONTROL = 0x03;

export const NOTIF_GATE_STATE = 1;
export const NOTIF_ROOT_KEY = 2;
export const NOTIF_ENABLED = 4;
export const NOTIF_PROPERTIES_LIST = 16;
export const NOTIF_PROPERTIES_LIST_END = 17;
export const NOTIF_PROPERTY_ACCEPTED = 18;
export const NOTIF_PROPERTIES_INVALID = 19;
export const NOTIF_LOG = 6;
export const NOTIF_LOG_END = 7;
export const NOTIF_SERVICE_DATA = 27;
export const NOTIF_SERVICE_DATA_END = 28;

export const ENCRYPTED_ACK_CONTINUE = 1;
export const ENCRYPTED_ACK_COMPLETE = 2;
export const ENCRYPTED_ACK_ERROR = 3;

export const GET_PROPERTIES_COMMAND_ID = 0x0028;
export const SET_PROPERTIES_COMMAND_ID = 0x0029;
export const GET_SELECTED_PROPERTIES_COMMAND_ID = 0x002c;
export const GET_LOG_COMMAND_ID = 0x0021;
export const READ_SERVICE_DATA_COMMAND_ID = 0x0042;
export const REGISTER_ROOT_COMMAND_ID = 0x0001;

export const SIZE_SIGNATURE = 32;
export const SIZE_ROOT_KEY = 32;
export const SIZE_USER_NAME = 16;
export const DEFAULT_REGISTER_USERNAME = 'ArnoNym';

/** Named gate action -> channel number. Only `impulse` (the factory-default
 * toggle) is verified against real hardware; the rest are derived from the
 * decompiled defaults table - the UI must not present them as certain. */
export const GATE_ACTIONS = {
  impulse: 1,
  light: 2,
  partial: 3,
  open: 4,
  close: 5,
  ventilation: 6,
} as const;

export type GateAction = keyof typeof GATE_ACTIONS;

export const CHANNEL_COMMAND_ID: Record<number, number> = {
  1: 0x0011,
  2: 0x0012,
  3: 0x0013,
  4: 0x0014,
  5: 0x0015,
  6: 0x0016,
};

/**
 * HMAC-SHA256 over a message, with the root key (or, during registration, the
 * register key) bound inside. Deliberately an interface rather than raw bytes:
 * the browser implementation wraps a non-extractable `CryptoKey`, so protocol
 * code never sees, and cannot leak, the key material.
 */
export interface Signer {
  sign(message: Uint8Array): Promise<Uint8Array>;
}

export function* chunk(data: Uint8Array, size: number = GATT_WRITE_CHUNK_SIZE): Generator<Uint8Array> {
  for (let i = 0; i < data.length; i += size) {
    yield data.subarray(i, Math.min(i + size, data.length));
  }
}

export function xorBytes(a: Uint8Array, b: Uint8Array): Uint8Array {
  const length = Math.min(a.length, b.length);
  const result = new Uint8Array(length);
  for (let i = 0; i < length; i++) result[i] = a[i] ^ b[i];
  return result;
}

/** Splits QR code content into the numeric prefix and the RSA
 * SubjectPublicKeyInfo DER block (base64 in the QR code). */
export function parseQrCode(text: string): { prefix: string; der: Uint8Array } {
  const trimmed = text.trim();
  let i = 0;
  while (i < trimmed.length && trimmed[i] >= '0' && trimmed[i] <= '9') i++;
  const prefix = trimmed.slice(0, i);
  const base64 = trimmed.slice(i);
  const binary = atob(base64);
  const der = new Uint8Array(binary.length);
  for (let j = 0; j < binary.length; j++) der[j] = binary.charCodeAt(j);
  return { prefix, der };
}

/** Serial number from the QR prefix. Returns null rather than guessing when the
 * layout does not match exactly - only the 31-digit version-3 layout is known. */
export function serialNoFromQrPrefix(prefix: string): bigint | null {
  if (prefix.length !== 31 || !/^\d+$/.test(prefix)) return null;
  return BigInt(prefix.slice(9, 29));
}

export function productClassAndIdFromQrPrefix(
  prefix: string,
): { productClass: number; productId: number } | null {
  if (prefix.length !== 31 || !/^\d+$/.test(prefix) || prefix.slice(0, 2) !== '03') return null;
  const productClass = Number.parseInt(prefix.slice(2, 4), 16);
  const productId = Number.parseInt(prefix.slice(4, 6), 16);
  if (Number.isNaN(productClass) || Number.isNaN(productId)) return null;
  return { productClass, productId };
}

/** `[0x02][len16 LE][32 random bytes, RSA-PKCS1v1.5-encrypted]` */
export function buildRegistrationFrame(rsaEncryptedKey: Uint8Array): Uint8Array {
  return concatBytes(
    new Uint8Array([ROUTING_ENCRYPTED]),
    uint16LE(rsaEncryptedKey.length + 3),
    rsaEncryptedKey,
  );
}

/** Final root key = value sent by the device XOR our registration random value. */
export function deriveRootKey(registerKey: Uint8Array, deviceWireValue: Uint8Array): Uint8Array {
  return xorBytes(deviceWireValue, registerKey);
}

/**
 * `[RootId(2 LE)][Command(2 LE)][Length incl. these 6 bytes(2 LE)][payload]
 * [HMAC-SHA256(key, everything above ++ challenge)(32)]`, wrapped in the outer
 * `[ioId][length]` envelope.
 */
async function buildSignedFrame(
  rootId: number,
  commandId: number,
  payload: Uint8Array,
  signer: Signer,
  challenge: Uint8Array,
): Promise<Uint8Array> {
  const lengthField = 6 + payload.length + SIZE_SIGNATURE;
  const header = concatBytes(uint16LE(rootId), uint16LE(commandId), uint16LE(lengthField));
  const message = concatBytes(header, payload);
  const signature = await signer.sign(concatBytes(message, challenge));
  const signed = concatBytes(message, signature);
  return concatBytes(new Uint8Array([ROUTING_SIGNED]), uint16LE(signed.length + 3), signed);
}

/** Second half of the registration: HMAC-signed with the same register key that
 * was RSA-encrypted for SET_REGISTER_KEY. RootId is 0 - the device has not told
 * us one yet. */
export function buildRegisterRootFrame(
  signer: Signer,
  challenge: Uint8Array,
  username: string = DEFAULT_REGISTER_USERNAME,
): Promise<Uint8Array> {
  const encoded = utf8(username).subarray(0, SIZE_USER_NAME);
  const usernameBytes = new Uint8Array(SIZE_USER_NAME);
  usernameBytes.set(encoded);
  const payload = concatBytes(new Uint8Array([0]), usernameBytes);
  return buildSignedFrame(0, REGISTER_ROOT_COMMAND_ID, payload, signer, challenge);
}

export function buildSwitchRelaisFrame(
  rootId: number,
  channel: number,
  signer: Signer,
  challenge: Uint8Array,
  now?: number,
): Promise<Uint8Array> {
  const commandId = CHANNEL_COMMAND_ID[channel];
  if (commandId === undefined) throw new Error(`channel must be 1..6, was ${channel}`);
  const timestamp = now ?? Math.floor(Date.now() / 1000);
  return buildSignedFrame(rootId, commandId, uint64LE(timestamp), signer, challenge);
}

export function buildGetPropertiesFrame(
  rootId: number,
  signer: Signer,
  challenge: Uint8Array,
): Promise<Uint8Array> {
  return buildSignedFrame(rootId, GET_PROPERTIES_COMMAND_ID, new Uint8Array(0), signer, challenge);
}

/** Payload is the raw menu-group bytes, padded with 0xFF to 4 entries. The
 * device drops the connection if a request mixes groups <100 and >=100 - use
 * {@link batchMenuGroupsForSelectedProperties} to build the batches. */
export function buildGetSelectedPropertiesFrame(
  rootId: number,
  menuGroups: readonly number[],
  signer: Signer,
  challenge: Uint8Array,
): Promise<Uint8Array> {
  if (menuGroups.length < 1 || menuGroups.length > 4) {
    throw new Error(`menuGroups must have 1..4 entries per request, had ${menuGroups.length}`);
  }
  const groups = new Uint8Array([...menuGroups, ...Array(4 - menuGroups.length).fill(0xff)]);
  return buildSignedFrame(rootId, GET_SELECTED_PROPERTIES_COMMAND_ID, groups, signer, challenge);
}

export function batchMenuGroupsForSelectedProperties(menuGroups: readonly number[]): number[][] {
  const sorted = [...menuGroups].sort((a, b) => a - b);
  const batches: number[][] = [];
  let current: number[] = [];
  for (let i = 0; i < sorted.length; i++) {
    const group = sorted[i];
    const crosses100 = i !== 0 && group >= 100 && sorted[i - 1] < 100;
    if (current.length > 0 && (current.length % 4 === 0 || crosses100)) {
      batches.push(current);
      current = [];
    }
    current.push(group);
  }
  if (current.length > 0) batches.push(current);
  return batches;
}

/** `[count(1)] + count * [menu_group(1), value(int16 LE, signed)]` */
export function buildSetPropertiesFrame(
  rootId: number,
  settings: readonly (readonly [number, number])[],
  signer: Signer,
  challenge: Uint8Array,
): Promise<Uint8Array> {
  if (settings.length === 0) throw new Error('settings must not be empty');
  const payload = new Uint8Array(1 + settings.length * 3);
  payload[0] = settings.length;
  const view = new DataView(payload.buffer);
  settings.forEach(([menuGroup, value], index) => {
    payload[1 + index * 3] = menuGroup;
    view.setInt16(2 + index * 3, value, true);
  });
  return buildSignedFrame(rootId, SET_PROPERTIES_COMMAND_ID, payload, signer, challenge);
}

export function buildGetLogFrame(
  rootId: number,
  signer: Signer,
  challenge: Uint8Array,
): Promise<Uint8Array> {
  return buildSignedFrame(rootId, GET_LOG_COMMAND_ID, new Uint8Array(0), signer, challenge);
}

export function buildReadServiceDataFrame(
  rootId: number,
  signer: Signer,
  challenge: Uint8Array,
): Promise<Uint8Array> {
  return buildSignedFrame(rootId, READ_SERVICE_DATA_COMMAND_ID, new Uint8Array(0), signer, challenge);
}

/**
 * Reassembles the outer `[ioId][length]` envelope.
 *
 * One BLE notify event can carry several messages back to back, and one message
 * can span several events - so `feed()` returns a list (possibly empty) of
 * complete messages and keeps the remainder for the next call. Never parse a
 * raw notification payload without going through this.
 */
export class NotificationReassembler {
  private static readonly VALID_IO_IDS = new Set([
    ROUTING_SIGNED,
    ROUTING_ENCRYPTED,
    ROUTING_BLUECONTROL,
  ]);

  private ioId: number | null = null;
  private declaredLength: number | null = null;
  private buffer: number[] = [];

  feed(data: Uint8Array): { ioId: number; payload: Uint8Array }[] {
    const results: { ioId: number; payload: Uint8Array }[] = [];
    let pos = 0;
    while (pos < data.length) {
      if (this.ioId === null) {
        if (data.length - pos < 3) break; // no longer a complete header - padding, discard
        const ioId = data[pos];
        const declaredLength = readUint16LE(data, pos + 1);
        if (!NotificationReassembler.VALID_IO_IDS.has(ioId) || declaredLength < 3) break;
        this.ioId = ioId;
        this.declaredLength = declaredLength;
        pos += 3;
      }
      const payloadSize = this.declaredLength! - 3;
      const needed = payloadSize - this.buffer.length;
      const take = Math.max(0, Math.min(needed, data.length - pos));
      for (let i = 0; i < take; i++) this.buffer.push(data[pos + i]);
      pos += take;
      if (this.buffer.length >= payloadSize) {
        results.push({ ioId: this.ioId, payload: new Uint8Array(this.buffer) });
        this.ioId = null;
        this.declaredLength = null;
        this.buffer = [];
      } else {
        break; // incomplete, the rest arrives in the next feed()
      }
    }
    return results;
  }
}

export interface LogEntry {
  logTag: number;
  timestampRaw: number;
  data: Uint8Array;
}

/**
 * A decoded notification of the Signed sub-protocol (ioId=1): 8-byte challenge
 * (nonce for the next signature), type (2), reserved (2), then type-specific
 * payload.
 */
export interface ParsedSignedNotification {
  challenge: Uint8Array;
  notifType: number;
  payload: Uint8Array;
  rootId: number | null;
  rootKeyWire: Uint8Array | null;
  properties: [number, number][] | null;
  logEntry: LogEntry | null;
  serviceData: [number, number][] | null;
}

export function parseSignedNotification(payload: Uint8Array): ParsedSignedNotification {
  if (payload.length < 12) {
    throw new Error(`Signed payload too short (${payload.length} bytes)`);
  }
  const challenge = payload.subarray(0, 8);
  const notifType = readUint16LE(payload, 8);
  const rest = payload.subarray(12);

  let rootId: number | null = null;
  let rootKeyWire: Uint8Array | null = null;
  let properties: [number, number][] | null = null;
  let logEntry: LogEntry | null = null;
  let serviceData: [number, number][] | null = null;

  if (notifType === NOTIF_ROOT_KEY && rest.length >= 2 + SIZE_ROOT_KEY) {
    rootId = readUint16LE(rest, 0);
    rootKeyWire = rest.subarray(2, 2 + SIZE_ROOT_KEY);
  } else if (notifType === NOTIF_PROPERTIES_LIST || notifType === NOTIF_PROPERTIES_LIST_END) {
    properties = parsePropertiesListPayload(rest);
  } else if (notifType === NOTIF_LOG || notifType === NOTIF_LOG_END) {
    logEntry = parseLogEntryPayload(rest);
  } else if (notifType === NOTIF_SERVICE_DATA || notifType === NOTIF_SERVICE_DATA_END) {
    serviceData = parseServiceDataPayload(rest);
  }

  return { challenge, notifType, payload: rest, rootId, rootKeyWire, properties, logEntry, serviceData };
}

/** `[count(1)] + count * [menu_group(1), value(int16 LE, signed)]` */
export function parsePropertiesListPayload(payload: Uint8Array): [number, number][] {
  if (payload.length === 0) return [];
  const count = payload[0];
  const settings: [number, number][] = [];
  let offset = 1;
  for (let i = 0; i < count; i++) {
    settings.push([payload[offset], readInt16LE(payload, offset + 1)]);
    offset += 3;
  }
  return settings;
}

/** `[dataLength(1)][logTag(1)][timestamp(uint32 LE)][data]` - one entry per
 * notification, unlike the list formats. */
export function parseLogEntryPayload(payload: Uint8Array): LogEntry | null {
  if (payload.length === 0) return null;
  const dataLength = payload[0];
  return {
    logTag: payload[1],
    timestampRaw: readUint32LE(payload, 2),
    data: payload.subarray(6, 6 + dataLength),
  };
}

/** `[count(1)] + count * [value(uint32 LE), serviceType(1)]` - note the
 * value/key order is swapped relative to the properties list. */
export function parseServiceDataPayload(payload: Uint8Array): [number, number][] {
  if (payload.length === 0 || payload[0] === 0) return [];
  const count = payload[0];
  const result: [number, number][] = [];
  let offset = 1;
  for (let i = 0; i < count; i++) {
    result.push([payload[offset + 4], readUint32LE(payload, offset)]);
    offset += 5;
  }
  return result;
}
