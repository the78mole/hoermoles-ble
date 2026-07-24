/**
 * High-level client, mirroring `hoermoles_ble.client.HoermannClient`: joins the
 * transport to the pure protocol logic and the crypto.
 *
 * The asynchronous shape differs from Python's asyncio version - there is no
 * `asyncio.Event`, so waiting for notifications is done with promise
 * subscribers on a small internal list. Behaviour is otherwise the same,
 * including the "challenge from the most recent notification" rule that every
 * signed command depends on.
 */

import { importRootKey, randomBytes, signerFromBytes, signerFromKey } from './crypto.js';
import { loadDevicePublicKey, rsaPkcs1v15Encrypt } from './rsa-pkcs1.js';
import {
  ENCRYPTED_ACK_COMPLETE,
  ENCRYPTED_ACK_CONTINUE,
  ENCRYPTED_ACK_ERROR,
  NOTIF_LOG_END,
  NOTIF_PROPERTIES_INVALID,
  NOTIF_PROPERTIES_LIST_END,
  NOTIF_PROPERTY_ACCEPTED,
  NOTIF_ROOT_KEY,
  NOTIF_SERVICE_DATA_END,
  NotificationReassembler,
  ROUTING_ENCRYPTED,
  ROUTING_SIGNED,
  batchMenuGroupsForSelectedProperties,
  buildGetLogFrame,
  buildGetPropertiesFrame,
  buildGetSelectedPropertiesFrame,
  buildReadServiceDataFrame,
  buildRegisterRootFrame,
  buildRegistrationFrame,
  buildSetPropertiesFrame,
  buildSwitchRelaisFrame,
  chunk,
  deriveRootKey,
  parseQrCode,
  parseSignedNotification,
  productClassAndIdFromQrPrefix,
  serialNoFromQrPrefix,
  type LogEntry,
  type ParsedSignedNotification,
} from './protocol.js';
import type { BleTransport, LogFn } from './transport.js';

/** The drive did not answer the registration. By far the most common cause is
 * that it already has an admin (advertisement bit `AdminsCanBeTeached=false`)
 * and needs a reset via menu 19/parameter 02 first. */
export class RegistrationTimeoutError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'RegistrationTimeoutError';
  }
}

export class PropertiesRejectedError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'PropertiesRejectedError';
  }
}

/** Everything needed to operate a drive. `key` is a `CryptoKey`, normally
 * non-extractable - the raw root key never has to exist in JS memory again
 * after import. */
export interface DriveCredentials {
  deviceAddress: string;
  rootId: number;
  key: CryptoKey;
}

/** Result of a successful registration - raw key material, because it still has
 * to be persisted and possibly exported. Import it and drop the bytes. */
export interface RegistrationResult {
  deviceAddress: string;
  rootId: number;
  rootKey: Uint8Array;
  qrPrefix: string;
  productClass: number | null;
  productId: number | null;
  serialNo: bigint | null;
}

type SignedSubscriber = (notification: ParsedSignedNotification) => void;
type EncryptedSubscriber = (status: number) => void;

const DEFAULT_TIMEOUT_MS = 10_000;

export class HoermannClient {
  private readonly transport: BleTransport;
  private readonly onLog: LogFn;
  private readonly reassembler = new NotificationReassembler();
  private readonly signedSubscribers = new Set<SignedSubscriber>();
  private readonly encryptedSubscribers = new Set<EncryptedSubscriber>();
  private lastSigned: ParsedSignedNotification | null = null;

  constructor(transport: BleTransport, onLog: LogFn = () => {}) {
    this.transport = transport;
    this.onLog = onLog;
  }

  async open(): Promise<void> {
    await this.transport.connect();
    await this.transport.startNotify((data) => this.handleNotification(data));
  }

  async close(): Promise<void> {
    await this.transport.stopNotify();
    await this.transport.disconnect();
  }

  /** The nonce for the next signed command, taken from the most recent
   * notification. All-zero until the drive has said anything - the Python
   * implementation does the same, and the drive rejects such a frame. */
  get challenge(): Uint8Array {
    return this.lastSigned?.challenge ?? new Uint8Array(8);
  }

  private handleNotification(data: Uint8Array): void {
    for (const { ioId, payload } of this.reassembler.feed(data)) {
      if (ioId === ROUTING_SIGNED) {
        let notification: ParsedSignedNotification;
        try {
          notification = parseSignedNotification(payload);
        } catch (error) {
          this.onLog(`WARNING: ${(error as Error).message}`);
          continue;
        }
        this.lastSigned = notification;
        for (const subscriber of [...this.signedSubscribers]) subscriber(notification);
      } else if (ioId === ROUTING_ENCRYPTED) {
        const status = payload.length > 0 ? payload[0] : -1;
        this.onLog(`Encrypted acknowledgement status=${status}`);
        for (const subscriber of [...this.encryptedSubscribers]) subscriber(status);
      } else {
        this.onLog(`Notification with unhandled ioId=${ioId}`);
      }
    }
  }

  /** Resolves on the first Signed notification matching `predicate`. */
  private waitForSigned(
    predicate: (n: ParsedSignedNotification) => boolean,
    timeoutMs = DEFAULT_TIMEOUT_MS,
  ): Promise<ParsedSignedNotification> {
    return new Promise((resolve, reject) => {
      const subscriber: SignedSubscriber = (notification) => {
        if (!predicate(notification)) return;
        cleanup();
        resolve(notification);
      };
      const timer = setTimeout(() => {
        cleanup();
        reject(new Error(`Timed out after ${timeoutMs} ms waiting for a notification`));
      }, timeoutMs);
      const cleanup = () => {
        clearTimeout(timer);
        this.signedSubscribers.delete(subscriber);
      };
      this.signedSubscribers.add(subscriber);
    });
  }

  /**
   * Collects every Signed notification up to and including the first one
   * matching `isLast`. Needed for multi-chunk answers (PROPERTIES_LIST...END):
   * chunks arrive back to back, and a single-slot "latest notification" cache
   * would silently drop the ones in between.
   */
  private collectSignedUntil(
    isLast: (n: ParsedSignedNotification) => boolean,
    timeoutMs = DEFAULT_TIMEOUT_MS,
  ): Promise<ParsedSignedNotification[]> {
    return new Promise((resolve, reject) => {
      const collected: ParsedSignedNotification[] = [];
      const subscriber: SignedSubscriber = (notification) => {
        collected.push(notification);
        if (!isLast(notification)) return;
        cleanup();
        resolve(collected);
      };
      const timer = setTimeout(() => {
        cleanup();
        reject(
          new Error(`Timed out after ${timeoutMs} ms waiting for the end of a multi-part response`),
        );
      }, timeoutMs);
      const cleanup = () => {
        clearTimeout(timer);
        this.signedSubscribers.delete(subscriber);
      };
      this.signedSubscribers.add(subscriber);
    });
  }

  /** Waits for the EncryptedIO acknowledgement: 1 = keep waiting, 2 = done,
   * 3 = error. */
  private waitForEncryptedComplete(timeoutMs = 20_000): Promise<void> {
    return new Promise((resolve, reject) => {
      const subscriber: EncryptedSubscriber = (status) => {
        if (status === ENCRYPTED_ACK_CONTINUE) return; // device restarted its timer
        cleanup();
        if (status === ENCRYPTED_ACK_COMPLETE) resolve();
        else if (status === ENCRYPTED_ACK_ERROR) {
          reject(
            new RegistrationTimeoutError(
              'The drive acknowledged SET_REGISTER_KEY with an error status.',
            ),
          );
        } else reject(new Error(`Unexpected encrypted acknowledgement status ${status}`));
      };
      const timer = setTimeout(() => {
        cleanup();
        reject(
          new RegistrationTimeoutError(
            'No acknowledgement received for SET_REGISTER_KEY - the drive is presumably not ' +
              'accepting a new registration right now (AdminsCanBeTeached=false). Reset it via ' +
              'menu 19/parameter 02 and try again.',
          ),
        );
      }, timeoutMs);
      const cleanup = () => {
        clearTimeout(timer);
        this.encryptedSubscribers.delete(subscriber);
      };
      this.encryptedSubscribers.add(subscriber);
    });
  }

  /** Waits for the first notification after connecting (typically ENABLED),
   * which is what supplies the initial challenge. */
  waitForAnyNotification(timeoutMs = DEFAULT_TIMEOUT_MS): Promise<ParsedSignedNotification> {
    return this.waitForSigned(() => true, timeoutMs);
  }

  /**
   * Writes a frame in 20-byte chunks with nothing in between.
   *
   * Deliberately no delay: the drive was observed live to disconnect roughly
   * 100-150 ms after the *first* chunk regardless of how many follow, i.e. it
   * enforces a time budget for the whole message. Adding pacing here makes
   * things strictly worse.
   */
  private async writeChunked(frame: Uint8Array): Promise<void> {
    for (const part of chunk(frame)) {
      await this.transport.write(part);
    }
  }

  /**
   * One-time QR code registration. Requires the drive to be accepting a new
   * registration (advertisement bit `AdminsCanBeTeached=true`, e.g. right after
   * a reset via menu 19/parameter 02).
   *
   * Two commands in sequence, exactly as `KeyChain.RegisterRoot` does: the
   * RSA-encrypted SET_REGISTER_KEY first, then - only after its acknowledgement -
   * REGISTER_ROOT signed with the same register key.
   */
  async register(
    qrText: string,
    deviceAddress: string,
    timeoutMs = 15_000,
  ): Promise<RegistrationResult> {
    const { prefix, der } = parseQrCode(qrText);
    const publicKey = await loadDevicePublicKey(der);
    const registerKey = randomBytes(32);
    const encrypted = rsaPkcs1v15Encrypt(publicKey, registerKey);
    this.onLog(`QR prefix: ${prefix}, RSA key: ${publicKey.sizeBytes * 8} bit`);

    const encryptedAck = this.waitForEncryptedComplete();
    await this.writeChunked(buildRegistrationFrame(encrypted));
    await encryptedAck;

    const registerSigner = await signerFromBytes(registerKey);
    const rootKeyNotification = this.waitForSigned((n) => n.notifType === NOTIF_ROOT_KEY, timeoutMs);
    await this.writeChunked(await buildRegisterRootFrame(registerSigner, this.challenge));

    let notification: ParsedSignedNotification;
    try {
      notification = await rootKeyNotification;
    } catch (error) {
      throw new RegistrationTimeoutError(
        `No ROOT_KEY notification received after REGISTER_ROOT (${(error as Error).message}).`,
      );
    }
    if (!notification.rootKeyWire || notification.rootId === null) {
      throw new RegistrationTimeoutError('ROOT_KEY notification did not carry a root key.');
    }

    const product = productClassAndIdFromQrPrefix(prefix);
    return {
      deviceAddress,
      rootId: notification.rootId,
      rootKey: deriveRootKey(registerKey, notification.rootKeyWire),
      qrPrefix: prefix,
      productClass: product?.productClass ?? null,
      productId: product?.productId ?? null,
      serialNo: serialNoFromQrPrefix(prefix),
    };
  }

  /** Sends a signed channel command (open/close/impulse/...). Call
   * `waitForAnyNotification()` first so the challenge is fresh. */
  async openChannel(credentials: DriveCredentials, channel = 1): Promise<void> {
    const signer = signerFromKey(credentials.key);
    const frame = await buildSwitchRelaisFrame(credentials.rootId, channel, signer, this.challenge);
    await this.writeChunked(frame);
  }

  /** Reads menu/parameter values. Without `menuGroups`, reads the whole table
   * (GET_PROPERTIES); with them, only those wire bytes, batched to respect the
   * drive's <100/>=100 boundary rule. */
  async readProperties(
    credentials: DriveCredentials,
    menuGroups?: readonly number[],
    timeoutMs = 20_000,
  ): Promise<Map<number, number>> {
    const signer = signerFromKey(credentials.key);
    const batches: (number[] | null)[] =
      menuGroups === undefined ? [null] : batchMenuGroupsForSelectedProperties(menuGroups);
    const results = new Map<number, number>();

    for (const batch of batches) {
      const frame =
        batch === null
          ? await buildGetPropertiesFrame(credentials.rootId, signer, this.challenge)
          : await buildGetSelectedPropertiesFrame(credentials.rootId, batch, signer, this.challenge);
      const collected = this.collectSignedUntil(
        (n) => n.notifType === NOTIF_PROPERTIES_LIST_END,
        timeoutMs,
      );
      await this.writeChunked(frame);
      for (const notification of await collected) {
        for (const [group, value] of notification.properties ?? []) results.set(group, value);
      }
    }
    return results;
  }

  /**
   * Writes menu/parameter values, batched into groups of at most 4 like the
   * official app.
   *
   * NOT verified against real hardware - unlike the read direction. A wrong
   * menu_group writes to the wrong parameter, so read the current value back
   * first and check it against the printed manual.
   */
  async writeProperties(
    credentials: DriveCredentials,
    settings: ReadonlyMap<number, number>,
    timeoutMs = 20_000,
  ): Promise<void> {
    const signer = signerFromKey(credentials.key);
    const items = [...settings.entries()];
    for (let i = 0; i < items.length; i += 4) {
      const batch = items.slice(i, i + 4) as [number, number][];
      const frame = await buildSetPropertiesFrame(credentials.rootId, batch, signer, this.challenge);
      const collected = this.collectSignedUntil(
        (n) => n.notifType === NOTIF_PROPERTY_ACCEPTED || n.notifType === NOTIF_PROPERTIES_INVALID,
        timeoutMs,
      );
      await this.writeChunked(frame);
      const notifications = await collected;
      if (notifications.at(-1)?.notifType === NOTIF_PROPERTIES_INVALID) {
        throw new PropertiesRejectedError(
          `Drive rejected property batch ${batch.map(([g, v]) => `${g}=${v}`).join(', ')}`,
        );
      }
    }
  }

  /** Reads the drive's security/access audit log. */
  async readLog(credentials: DriveCredentials, timeoutMs = 20_000): Promise<LogEntry[]> {
    const signer = signerFromKey(credentials.key);
    const frame = await buildGetLogFrame(credentials.rootId, signer, this.challenge);
    const collected = this.collectSignedUntil((n) => n.notifType === NOTIF_LOG_END, timeoutMs);
    await this.writeChunked(frame);
    return (await collected).map((n) => n.logEntry).filter((entry): entry is LogEntry => entry !== null);
  }

  /** Reads the diagnostics counters (operating hours, door cycles, ...). */
  async readServiceData(
    credentials: DriveCredentials,
    timeoutMs = 20_000,
  ): Promise<Map<number, number>> {
    const signer = signerFromKey(credentials.key);
    const frame = await buildReadServiceDataFrame(credentials.rootId, signer, this.challenge);
    const collected = this.collectSignedUntil((n) => n.notifType === NOTIF_SERVICE_DATA_END, timeoutMs);
    await this.writeChunked(frame);
    const results = new Map<number, number>();
    for (const notification of await collected) {
      for (const [type, value] of notification.serviceData ?? []) results.set(type, value);
    }
    return results;
  }
}

/** Turns raw key material into usable credentials, importing the key
 * non-extractably by default. */
export async function credentialsFromRootKey(
  deviceAddress: string,
  rootId: number,
  rootKey: Uint8Array,
): Promise<DriveCredentials> {
  return { deviceAddress, rootId, key: await importRootKey(rootKey) };
}
