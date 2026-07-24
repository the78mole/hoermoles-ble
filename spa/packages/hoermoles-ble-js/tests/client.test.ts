/**
 * Client behaviour against a fake transport.
 *
 * This is where the transport interface earns its keep: everything below the
 * radio - challenge handling, chunked writes, multi-part response collection,
 * the registration handshake ordering - is exercised without a browser or a
 * drive. What is NOT covered here, and cannot be, is the real timing behaviour
 * of Web Bluetooth writes; that needs hardware (see SPA_PLAN.md, Spike 1).
 */

import { describe, expect, it, vi } from 'vitest';

import { concatBytes, fromHex, toHex, uint16LE } from '../src/bytes.js';
import { HoermannClient, credentialsFromRootKey } from '../src/client.js';
import {
  GATT_WRITE_CHUNK_SIZE,
  NOTIF_LOG,
  NOTIF_LOG_END,
  NOTIF_PROPERTIES_INVALID,
  NOTIF_PROPERTIES_LIST,
  NOTIF_PROPERTIES_LIST_END,
  NOTIF_PROPERTY_ACCEPTED,
  ROUTING_ENCRYPTED,
  ROUTING_SIGNED,
} from '../src/protocol.js';
import type { BleTransport } from '../src/transport.js';

/** Records every chunk written and lets a test push notifications back. */
class FakeTransport implements BleTransport {
  writes: Uint8Array[] = [];
  connected = false;
  private notify: ((data: Uint8Array) => void) | null = null;

  async connect(): Promise<void> {
    this.connected = true;
  }
  async disconnect(): Promise<void> {
    this.connected = false;
  }
  async write(data: Uint8Array): Promise<void> {
    this.writes.push(new Uint8Array(data));
  }
  async startNotify(callback: (data: Uint8Array) => void): Promise<void> {
    this.notify = callback;
  }
  async stopNotify(): Promise<void> {
    this.notify = null;
  }

  /** Delivers a raw notify event, envelope included. */
  emit(ioId: number, payload: Uint8Array): void {
    this.notify?.(concatBytes(new Uint8Array([ioId]), uint16LE(payload.length + 3), payload));
  }

  /** Delivers a Signed notification with the given challenge and type. */
  emitSigned(notifType: number, challenge: string, body: Uint8Array = new Uint8Array(0)): void {
    this.emit(ROUTING_SIGNED, concatBytes(fromHex(challenge), uint16LE(notifType), uint16LE(0), body));
  }

  get writtenFrame(): string {
    return toHex(concatBytes(...this.writes));
  }
}

/** Numeric sort - Array#sort would compare "101" < "99" as strings. */
function sortedEntries(map: Map<number, number>): [number, number][] {
  return [...map.entries()].sort(([a], [b]) => a - b);
}

const ROOT_KEY = new Uint8Array(32).fill(0x11);
const CHALLENGE_A = '0011223344556677';
const CHALLENGE_B = 'aabbccddeeff0011';

async function connectedClient(): Promise<{ transport: FakeTransport; client: HoermannClient }> {
  const transport = new FakeTransport();
  const client = new HoermannClient(transport);
  await client.open();
  return { transport, client };
}

describe('challenge handling', () => {
  it('is all-zero before the drive has said anything', async () => {
    const { client } = await connectedClient();
    expect(toHex(client.challenge)).toBe('0000000000000000');
  });

  it('tracks the most recent notification', async () => {
    const { transport, client } = await connectedClient();
    transport.emitSigned(4, CHALLENGE_A);
    expect(toHex(client.challenge)).toBe(CHALLENGE_A);

    transport.emitSigned(1, CHALLENGE_B);
    expect(toHex(client.challenge)).toBe(CHALLENGE_B);
  });

  it('waitForAnyNotification resolves on the first one', async () => {
    const { transport, client } = await connectedClient();
    const pending = client.waitForAnyNotification();
    transport.emitSigned(4, CHALLENGE_A);
    expect(toHex((await pending).challenge)).toBe(CHALLENGE_A);
  });

  it('waitForAnyNotification rejects on timeout', async () => {
    vi.useFakeTimers();
    try {
      const { client } = await connectedClient();
      const pending = client.waitForAnyNotification(1000);
      const assertion = expect(pending).rejects.toThrow(/Timed out/);
      await vi.advanceTimersByTimeAsync(1001);
      await assertion;
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('writes', () => {
  it('splits a frame into 20-byte chunks with nothing in between', async () => {
    const { transport, client } = await connectedClient();
    transport.emitSigned(4, CHALLENGE_A);

    const credentials = await credentialsFromRootKey('AA:BB:CC:DD:EE:FF', 1, ROOT_KEY);
    await client.openChannel(credentials, 1);

    // 3 envelope + 6 header + 8 timestamp + 32 signature = 49 bytes -> 20/20/9
    expect(transport.writes.map((w) => w.length)).toEqual([20, 20, 9]);
    for (const write of transport.writes.slice(0, -1)) {
      expect(write.length).toBe(GATT_WRITE_CHUNK_SIZE);
    }
  });

  it('signs with the current challenge', async () => {
    const { transport, client } = await connectedClient();
    const credentials = await credentialsFromRootKey('AA:BB:CC:DD:EE:FF', 1, ROOT_KEY);

    transport.emitSigned(4, CHALLENGE_A);
    await client.openChannel(credentials, 1);
    const first = transport.writtenFrame;

    transport.writes = [];
    transport.emitSigned(4, CHALLENGE_B);
    await client.openChannel(credentials, 1);

    // Same command, different challenge -> different signature. If this ever
    // passes as equal, the challenge is not reaching the HMAC.
    expect(transport.writtenFrame).not.toBe(first);
  });

  it('rejects an out-of-range channel', async () => {
    const { client } = await connectedClient();
    const credentials = await credentialsFromRootKey('AA:BB:CC:DD:EE:FF', 1, ROOT_KEY);
    await expect(client.openChannel(credentials, 9)).rejects.toThrow(/channel must be 1\.\.6/);
  });
});

describe('multi-part responses', () => {
  it('collects every PROPERTIES_LIST chunk, not just the last', async () => {
    const { transport, client } = await connectedClient();
    transport.emitSigned(4, CHALLENGE_A);
    const credentials = await credentialsFromRootKey('AA:BB:CC:DD:EE:FF', 1, ROOT_KEY);

    const pending = client.readProperties(credentials);
    await vi.waitFor(() => expect(transport.writes.length).toBeGreaterThan(0));

    // Two chunks back to back, then the terminator carrying a final entry -
    // a single-slot "latest notification" cache would lose the middle one.
    transport.emitSigned(NOTIF_PROPERTIES_LIST, CHALLENGE_A, fromHex('01' + '01' + '0500'));
    transport.emitSigned(NOTIF_PROPERTIES_LIST, CHALLENGE_A, fromHex('01' + '02' + '0700'));
    transport.emitSigned(NOTIF_PROPERTIES_LIST_END, CHALLENGE_A, fromHex('01' + '03' + 'ffff'));

    const values = await pending;
    expect(sortedEntries(values)).toEqual([
      [1, 5],
      [2, 7],
      [3, -1],
    ]);
  });

  it('batches selected-property requests across the group-100 boundary', async () => {
    const { transport, client } = await connectedClient();
    transport.emitSigned(4, CHALLENGE_A);
    const credentials = await credentialsFromRootKey('AA:BB:CC:DD:EE:FF', 1, ROOT_KEY);

    const pending = client.readProperties(credentials, [99, 100, 101]);
    // Two batches: [99] then [100, 101] - mixing them makes a real drive hang up.
    await vi.waitFor(() => expect(transport.writes.length).toBeGreaterThan(0));
    transport.emitSigned(NOTIF_PROPERTIES_LIST_END, CHALLENGE_A, fromHex('01' + '63' + '0100'));
    await vi.waitFor(() => expect(transport.writes.length).toBeGreaterThan(3));
    transport.emitSigned(NOTIF_PROPERTIES_LIST_END, CHALLENGE_A, fromHex('01' + '65' + '0200'));

    expect(sortedEntries(await pending)).toEqual([
      [99, 1],
      [101, 2],
    ]);
  });

  it('collects log entries and drops the empty terminator', async () => {
    const { transport, client } = await connectedClient();
    transport.emitSigned(4, CHALLENGE_A);
    const credentials = await credentialsFromRootKey('AA:BB:CC:DD:EE:FF', 1, ROOT_KEY);

    const pending = client.readLog(credentials);
    await vi.waitFor(() => expect(transport.writes.length).toBeGreaterThan(0));
    transport.emitSigned(NOTIF_LOG, CHALLENGE_A, fromHex('02' + '05' + '78563412' + 'abcd'));
    transport.emitSigned(NOTIF_LOG_END, CHALLENGE_A);

    const entries = await pending;
    expect(entries).toHaveLength(1);
    expect(entries[0].logTag).toBe(5);
    expect(entries[0].timestampRaw).toBe(0x12345678);
    expect(toHex(entries[0].data)).toBe('abcd');
  });

  it('throws when the drive rejects a property write', async () => {
    const { transport, client } = await connectedClient();
    transport.emitSigned(4, CHALLENGE_A);
    const credentials = await credentialsFromRootKey('AA:BB:CC:DD:EE:FF', 1, ROOT_KEY);

    const pending = client.writeProperties(credentials, new Map([[16, 99]]));
    await vi.waitFor(() => expect(transport.writes.length).toBeGreaterThan(0));
    transport.emitSigned(NOTIF_PROPERTIES_INVALID, CHALLENGE_A);

    await expect(pending).rejects.toThrow(/rejected property batch 16=99/);
  });

  it('accepts a property write the drive acknowledges', async () => {
    const { transport, client } = await connectedClient();
    transport.emitSigned(4, CHALLENGE_A);
    const credentials = await credentialsFromRootKey('AA:BB:CC:DD:EE:FF', 1, ROOT_KEY);

    const pending = client.writeProperties(credentials, new Map([[16, 1]]));
    await vi.waitFor(() => expect(transport.writes.length).toBeGreaterThan(0));
    transport.emitSigned(NOTIF_PROPERTY_ACCEPTED, CHALLENGE_A);

    await expect(pending).resolves.toBeUndefined();
  });
});

describe('malformed traffic', () => {
  it('ignores an undersized Signed payload instead of throwing', async () => {
    const logs: string[] = [];
    const transport = new FakeTransport();
    const client = new HoermannClient(transport, (message) => logs.push(message));
    await client.open();

    transport.emit(ROUTING_SIGNED, fromHex('0011223344'));
    expect(logs.some((line) => line.includes('too short'))).toBe(true);
    expect(toHex(client.challenge)).toBe('0000000000000000');
  });

  it('reports an unknown routing id without failing', async () => {
    const logs: string[] = [];
    const transport = new FakeTransport();
    const client = new HoermannClient(transport, (message) => logs.push(message));
    await client.open();

    transport.emit(3, fromHex('0102030405060708090a0b0c'));
    expect(logs.some((line) => line.includes('unhandled ioId=3'))).toBe(true);
  });

  it('surfaces an encrypted error acknowledgement during registration', async () => {
    const transport = new FakeTransport();
    const client = new HoermannClient(transport);
    await client.open();

    const keyPair = await crypto.subtle.generateKey(
      {
        name: 'RSA-OAEP',
        modulusLength: 1024,
        publicExponent: new Uint8Array([1, 0, 1]),
        hash: 'SHA-256',
      },
      true,
      ['encrypt', 'decrypt'],
    );
    const spki = new Uint8Array(await crypto.subtle.exportKey('spki', keyPair.publicKey));
    const qrText = '0302020000003026260264145103079' + btoa(String.fromCharCode(...spki));

    const pending = client.register(qrText, 'AA:BB:CC:DD:EE:FF');
    await vi.waitFor(() => expect(transport.writes.length).toBeGreaterThan(0));
    transport.emit(ROUTING_ENCRYPTED, new Uint8Array([3])); // ENCRYPTED_ACK_ERROR

    await expect(pending).rejects.toThrow(/error status/);
  });
});
