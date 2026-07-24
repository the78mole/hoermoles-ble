/**
 * Credential persistence, and specifically the property the whole design rests
 * on: that a stored root key is unreadable.
 *
 * `fake-indexeddb` provides a real IndexedDB implementation in Node, including
 * structured clone - which matters here, because storing a `CryptoKey` at all
 * depends on structured clone supporting it.
 */

import 'fake-indexeddb/auto';

import { beforeEach, describe, expect, it } from 'vitest';

import { toHex } from '../src/bytes.js';
import { exportRootKey } from '../src/crypto.js';
import {
  clearCredentials,
  deleteCredential,
  getCredential,
  isIndexedDbAvailable,
  listCredentials,
  requestPersistentStorage,
  saveCredential,
} from '../src/store.js';

const ROOT_KEY = new Uint8Array(32).fill(0x5a);

function entry(deviceAddress = 'aa:bb:cc:dd:ee:ff') {
  return {
    deviceAddress,
    rootId: 1,
    rootKey: new Uint8Array(ROOT_KEY),
    productClass: 2,
    productId: 2,
    productName: 'Supramatic Serie 4',
    serialNo: '302626026414510307',
  };
}

beforeEach(async () => {
  await clearCredentials();
});

describe('storing and reading back', () => {
  it('reports IndexedDB as available under the test shim', () => {
    expect(isIndexedDbAvailable()).toBe(true);
  });

  it('round-trips a credential', async () => {
    await saveCredential(entry());
    const record = await getCredential('AA:BB:CC:DD:EE:FF');

    expect(record).not.toBeNull();
    expect(record!.rootId).toBe(1);
    expect(record!.productName).toBe('Supramatic Serie 4');
    expect(record!.serialNo).toBe('302626026414510307');
    expect(record!.createdUnix).toBeGreaterThan(0);
  });

  it('normalises the address to upper case, so lookups are case-insensitive', async () => {
    await saveCredential(entry('aa:bb:cc:dd:ee:ff'));
    expect((await getCredential('aa:bb:cc:dd:ee:ff'))?.deviceAddress).toBe('AA:BB:CC:DD:EE:FF');
    expect(await getCredential('AA:BB:CC:DD:EE:FF')).not.toBeNull();
  });

  it('returns null for an unknown drive', async () => {
    expect(await getCredential('11:22:33:44:55:66')).toBeNull();
  });

  it('lists credentials sorted by address', async () => {
    await saveCredential(entry('FF:FF:FF:FF:FF:FF'));
    await saveCredential(entry('11:11:11:11:11:11'));
    expect((await listCredentials()).map((r) => r.deviceAddress)).toEqual([
      '11:11:11:11:11:11',
      'FF:FF:FF:FF:FF:FF',
    ]);
  });

  it('overwrites an existing entry for the same drive', async () => {
    await saveCredential(entry());
    await saveCredential({ ...entry(), rootId: 42 });
    expect((await listCredentials()).length).toBe(1);
    expect((await getCredential('AA:BB:CC:DD:EE:FF'))?.rootId).toBe(42);
  });

  it('deletes a credential', async () => {
    await saveCredential(entry());
    await deleteCredential('AA:BB:CC:DD:EE:FF');
    expect(await getCredential('AA:BB:CC:DD:EE:FF')).toBeNull();
  });
});

describe('key extractability - the security property', () => {
  it('stores a non-extractable key by default, and no raw copy', async () => {
    const record = await saveCredential(entry());

    expect(record.key.extractable).toBe(false);
    expect(record.rootKey).toBeUndefined();

    // This is the whole point: even holding the record, the bytes are gone.
    await expect(exportRootKey(record.key)).rejects.toThrow(/cannot be exported/);
  });

  it('survives the IndexedDB round trip as a still-unusable-for-export key', async () => {
    await saveCredential(entry());
    const stored = await getCredential('AA:BB:CC:DD:EE:FF');

    expect(stored!.key).toBeInstanceOf(CryptoKey);
    expect(stored!.key.extractable).toBe(false);
    expect(stored!.rootKey).toBeUndefined();
  });

  it('can still sign with a non-extractable key', async () => {
    const record = await saveCredential(entry());
    const signature = await crypto.subtle.sign('HMAC', record.key, new Uint8Array([1, 2, 3]));
    expect(signature.byteLength).toBe(32);
  });

  it('keeps a readable copy only when re-export was explicitly requested', async () => {
    const record = await saveCredential(entry(), { allowReexport: true });

    expect(record.key.extractable).toBe(true);
    expect(toHex(record.rootKey!)).toBe(toHex(ROOT_KEY));
    expect(toHex(await exportRootKey(record.key))).toBe(toHex(ROOT_KEY));
  });

  it('preserves the re-export choice across the round trip', async () => {
    await saveCredential(entry(), { allowReexport: true });
    const stored = await getCredential('AA:BB:CC:DD:EE:FF');
    expect(toHex(stored!.rootKey!)).toBe(toHex(ROOT_KEY));
  });

  it('stores a label when given one', async () => {
    const record = await saveCredential(entry(), { label: 'Garage' });
    expect(record.label).toBe('Garage');
  });
});

describe('persistent storage request', () => {
  it('returns false when the Storage API is absent, rather than throwing', async () => {
    // Node has no navigator.storage; the app must degrade quietly, because a
    // refused persistence request is normal in a plain browser tab too.
    await expect(requestPersistentStorage()).resolves.toBe(false);
  });
});
