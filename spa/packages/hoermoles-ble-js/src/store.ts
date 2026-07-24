/**
 * Persistent credential storage in IndexedDB.
 *
 * The design point worth understanding: what gets stored is a `CryptoKey`, not
 * key bytes. `CryptoKey` is structured-cloneable, so IndexedDB accepts it
 * directly, and when it was imported with `extractable: false` the raw root key
 * is unreachable afterwards - by this code and by anything injected into the
 * page later. The stored record can sign door commands forever but cannot be
 * turned back into a transferable secret.
 *
 * That deliberately breaks re-export, so {@link saveCredential} takes an
 * explicit `allowReexport` flag. When set, the raw bytes are kept alongside the
 * key; when not (the default), they are not stored at all. The UI must state
 * which one the user is choosing.
 *
 * Storage is per-origin and can be evicted by the browser under storage
 * pressure - so this is a cache of a credential, never its only copy. Users must
 * be told to keep the CLI export or the QR code.
 */

import { importRootKey, importRootKeyExportable } from './crypto.js';

const DB_NAME = 'hoermoles';
const DB_VERSION = 1;
const CREDENTIAL_STORE = 'credentials';

/** One taught drive as persisted. `rootKey` is present only when the user opted
 * into re-export. */
export interface StoredCredential {
  deviceAddress: string;
  rootId: number;
  key: CryptoKey;
  rootKey?: Uint8Array;
  label?: string;
  qrPrefix?: string;
  productClass?: number;
  productId?: number;
  productName?: string | null;
  /** uint64 as a decimal string - never a number, see bundle.ts. */
  serialNo?: string | null;
  createdUnix: number;
}

export function isIndexedDbAvailable(): boolean {
  return typeof indexedDB !== 'undefined';
}

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(CREDENTIAL_STORE)) {
        db.createObjectStore(CREDENTIAL_STORE, { keyPath: 'deviceAddress' });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error('Could not open IndexedDB'));
  });
}

function promisify<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error('IndexedDB request failed'));
  });
}

async function withStore<T>(
  mode: IDBTransactionMode,
  action: (store: IDBObjectStore) => Promise<T>,
): Promise<T> {
  const db = await openDatabase();
  try {
    return await action(db.transaction(CREDENTIAL_STORE, mode).objectStore(CREDENTIAL_STORE));
  } finally {
    db.close();
  }
}

export interface SaveOptions {
  /** Keep the raw root key so this credential can be exported again later.
   * Off by default - see the module docstring for why that matters. */
  allowReexport?: boolean;
  label?: string;
}

/**
 * Imports raw key material and persists it. The caller should drop its own copy
 * of `rootKey` immediately afterwards; with `allowReexport` off there is then no
 * readable copy left anywhere.
 */
export async function saveCredential(
  entry: Omit<StoredCredential, 'key' | 'rootKey' | 'createdUnix'> & {
    rootKey: Uint8Array;
    createdUnix?: number;
  },
  options: SaveOptions = {},
): Promise<StoredCredential> {
  const { allowReexport = false, label } = options;
  const key = allowReexport
    ? await importRootKeyExportable(entry.rootKey)
    : await importRootKey(entry.rootKey);

  const record: StoredCredential = {
    deviceAddress: entry.deviceAddress.toUpperCase(),
    rootId: entry.rootId,
    key,
    label: label ?? entry.label,
    qrPrefix: entry.qrPrefix,
    productClass: entry.productClass,
    productId: entry.productId,
    productName: entry.productName ?? null,
    serialNo: entry.serialNo ?? null,
    createdUnix: entry.createdUnix ?? Math.floor(Date.now() / 1000),
  };
  if (allowReexport) record.rootKey = entry.rootKey;

  await withStore('readwrite', (store) => promisify(store.put(record)));
  return record;
}

export async function listCredentials(): Promise<StoredCredential[]> {
  const records = await withStore('readonly', (store) =>
    promisify(store.getAll() as IDBRequest<StoredCredential[]>),
  );
  return records.sort((a, b) => a.deviceAddress.localeCompare(b.deviceAddress));
}

export async function getCredential(deviceAddress: string): Promise<StoredCredential | null> {
  const record = await withStore('readonly', (store) =>
    promisify(store.get(deviceAddress.toUpperCase()) as IDBRequest<StoredCredential | undefined>),
  );
  return record ?? null;
}

/**
 * Renames a stored drive without re-importing its key.
 *
 * This is why rename is a store operation rather than a `saveCredential` with a
 * new label: `saveCredential` needs the raw root key to import, which we
 * deliberately do not keep for non-extractable credentials. Reading the record,
 * changing one field and putting it back preserves the exact same `CryptoKey`
 * (structured clone carries it), so a non-extractable key stays non-extractable.
 * An empty or whitespace-only name clears the label.
 */
export async function updateCredentialLabel(deviceAddress: string, label: string): Promise<void> {
  // Read and write in separate transactions on purpose: awaiting between a get
  // and a put inside one transaction can let it auto-commit in the gap (an
  // IndexedDB footgun - a transaction goes inactive once control returns to the
  // event loop with no pending request). The store is single-user and local, so
  // the read-then-write is not a meaningful race.
  const record = await getCredential(deviceAddress);
  if (!record) return;
  const trimmed = label.trim();
  record.label = trimmed === '' ? undefined : trimmed;
  await withStore('readwrite', (store) => promisify(store.put(record)));
}

export async function deleteCredential(deviceAddress: string): Promise<void> {
  await withStore('readwrite', (store) => promisify(store.delete(deviceAddress.toUpperCase())));
}

export async function clearCredentials(): Promise<void> {
  await withStore('readwrite', (store) => promisify(store.clear()));
}

/**
 * Asks the browser to make this origin's storage persistent, so credentials are
 * not evicted under storage pressure. Best effort - Chrome grants it silently
 * for installed PWAs and usually denies it for a plain tab. Returns whether
 * storage is persistent now.
 */
export async function requestPersistentStorage(): Promise<boolean> {
  if (typeof navigator === 'undefined' || !navigator.storage?.persist) return false;
  try {
    return (await navigator.storage.persisted()) || (await navigator.storage.persist());
  } catch {
    return false;
  }
}
