/**
 * The app's view of stored drives: a thin reactive layer over the IndexedDB
 * credential store, plus the import/export glue.
 *
 * Credentials are loaded once on start and kept in a rune-backed array so every
 * component sees the same list. The `CryptoKey` inside each record is normally
 * non-extractable, so this state can be passed around freely - it is a handle,
 * not a secret.
 */

import {
  bundleToJson,
  decodeBundle,
  deleteCredential,
  encodeBundle,
  exportRootKey,
  listCredentials,
  saveCredential,
  updateCredentialLabel,
  type BundleEntry,
  type DriveCredentials,
  type StoredCredential,
} from 'hoermoles-ble-js';

export const drives = $state<{ items: StoredCredential[]; loaded: boolean }>({
  items: [],
  loaded: false,
});

export async function refreshDrives(): Promise<void> {
  drives.items = await listCredentials();
  drives.loaded = true;
}

export function credentialsFor(record: StoredCredential): DriveCredentials {
  return { deviceAddress: record.deviceAddress, rootId: record.rootId, key: record.key };
}

export function displayName(record: StoredCredential): string {
  return record.label ?? record.productName ?? record.deviceAddress;
}

/** Sets or clears the user-facing name of a drive and refreshes the list. */
export async function renameDrive(deviceAddress: string, label: string): Promise<void> {
  await updateCredentialLabel(deviceAddress, label);
  await refreshDrives();
}

/**
 * Imports a bundle from any of its forms.
 *
 * `allowReexport` decides whether the raw root key is kept alongside the
 * non-extractable key. Off means this device can never hand the credential on -
 * which is the safer default, and the reason the UI has to ask rather than
 * silently pick.
 */
export async function importBundle(
  text: string,
  options: { passphrase?: string; allowReexport?: boolean } = {},
): Promise<StoredCredential[]> {
  const entries = await decodeBundle(text, options.passphrase);
  const saved: StoredCredential[] = [];
  for (const entry of entries) {
    saved.push(
      await saveCredential(
        {
          deviceAddress: entry.deviceAddress,
          rootId: entry.rootId,
          rootKey: entry.rootKey,
          label: entry.label ?? undefined,
          qrPrefix: entry.qrPrefix,
          productClass: entry.productClass,
          productId: entry.productId,
          productName: entry.productName,
          serialNo: entry.serialNo,
          createdUnix: entry.createdUnix || undefined,
        },
        { allowReexport: options.allowReexport ?? false },
      ),
    );
    // The bundle's plaintext copy has served its purpose - overwrite it rather
    // than leaving key material lying around in a reachable object.
    entry.rootKey.fill(0);
  }
  await refreshDrives();
  return saved;
}

async function toBundleEntry(record: StoredCredential): Promise<BundleEntry> {
  const rootKey = record.rootKey ?? (await exportRootKey(record.key));
  return {
    deviceAddress: record.deviceAddress,
    rootId: record.rootId,
    rootKey,
    label: record.label,
    qrPrefix: record.qrPrefix ?? '',
    createdUnix: record.createdUnix,
    productClass: record.productClass,
    productId: record.productId,
    productName: record.productName,
    serialNo: record.serialNo,
  };
}

export function isExportable(record: StoredCredential): boolean {
  return record.rootKey !== undefined || record.key.extractable;
}

/** Text form, for a QR code or a link. Throws for credentials stored
 * non-extractably - check {@link isExportable} first and say so in the UI. */
export async function exportBundleText(
  records: readonly StoredCredential[],
  passphrase?: string,
): Promise<string> {
  const entries = await Promise.all(records.map(toBundleEntry));
  return encodeBundle(entries, passphrase);
}

export async function exportBundleJson(records: readonly StoredCredential[]): Promise<string> {
  const entries = await Promise.all(records.map(toBundleEntry));
  return bundleToJson(entries);
}

export async function forgetDrive(deviceAddress: string): Promise<void> {
  await deleteCredential(deviceAddress);
  await refreshDrives();
}
